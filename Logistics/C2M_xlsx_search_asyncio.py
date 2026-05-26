import os
import re
import psycopg2
from psycopg2 import sql
from datetime import datetime
from openpyxl import load_workbook, __version__ as openpyxl_version # Импортируем версию для информации
from dotenv import load_dotenv
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

# --- Конфигурация ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(threadName)s] [%(funcName)s] %(message)s",
    handlers=[
        logging.FileHandler("excel_registry.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

load_dotenv()

DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD')
}

START_DIR = r'\\10.1.19.245\C2M Logistics\2025\CAINIAO'
# START_DIR = r'\\10.1.19.245\C2M Logistics\2025\CAINIAO\Опасники TRUCK  через OSS'
TABLE_NAME = 'public.excel_registry'
FILE_PATTERN = re.compile(r".*\.xlsx$", re.IGNORECASE)
PACKAGE_PATTERN = re.compile(r"-\s*(\d+).*?\((\d{2}\.\d{2}\.\d{4})\)") # - <число> ... (<дата в формате ДД.ММ.ГГГГ>)
# -	Буквально символ - (дефис)
# \s*	0 или более пробелов после дефиса
# (\d+)	Группа 1: одно или более цифр (например, номер пакета)
# .*?	Нежадный захват любых символов (в т.ч. пробелы и буквы)
# \(	Открывающая скобка (
# (\d{2}\.\d{2}\.\d{4})	Группа 2: дата в формате ДД.ММ.ГГГГ
# \)	Закрывающая скобка )

REQUIRED_COLUMNS = ["cartonid", "itemid", "masterno", "ordercode",
                   "consigneecountry", "service", "danger_type"]

REQUIRED_COLUMNS_SET = set(REQUIRED_COLUMNS)
MAX_WORKERS = int(os.getenv('MAX_SCAN_WORKERS', 10))

logging.info(f"Используется openpyxl версии: {openpyxl_version}")

# --- Функции ---

def check_required_columns(headers):
    """Проверяет наличие обязательных колонок в файле Excel (синхронная)"""
    if not headers:
        raise ValueError("Файл не содержит заголовков (пустая первая строка).")
    headers_lower_set = {str(h).strip().lower() for h in headers if h is not None}
    missing = list(REQUIRED_COLUMNS_SET - headers_lower_set)
    weight_present = any("weight" in col for col in headers_lower_set)
    if missing:
        raise ValueError(f"Отсутствуют обязательные колонки: {', '.join(sorted(missing))}")
    if not weight_present:
        raise ValueError("Не найдена колонка, содержащая 'weight'")

def get_file_metadata(file_path):
    """Получает метаданные файла (синхронная)"""
    try:
        file_stat = os.stat(file_path)
        return {
            'dt_create': datetime.fromtimestamp(file_stat.st_ctime),
            'dt_modified': datetime.fromtimestamp(file_stat.st_mtime),
            'size_kb': file_stat.st_size // 1024
        }
    except FileNotFoundError:
        logging.error(f"Файл не найден при получении метаданных: {file_path}")
        raise ValueError(f"Файл не найден: {file_path}")
    except PermissionError:
        logging.error(f"Ошибка доступа при получении метаданных: {file_path}")
        raise ValueError(f"Ошибка доступа к файлу: {file_path}")
    except Exception as e:
        logging.error(f"Неожиданная ошибка получения метаданных для {file_path}: {str(e)}")
        raise ValueError(f"Ошибка получения метаданных файла: {str(e)}")

def is_column_related_error(error_message: str) -> bool:
    """Проверяет, связана ли ошибка с отсутствием/неверным набором колонок."""
    if not error_message:
        return False
    
    # Приводим к нижнему регистру для регистронезависимого поиска подстроки
    error_message_lower = error_message.lower()

    # Проверяем по ключевым фразам, которые мы используем в check_required_columns
    result = (
        error_message.startswith("Отсутствуют обязательные колонки:") or
        error_message == "Не найдена колонка, содержащая 'weight'" or
        # Можно добавить другие варианты, если check_required_columns генерирует другие сообщения
        error_message.startswith("ValueError: Отсутствуют обязательные колонки:") or # Если ловится ValueError
        error_message == "ValueError: Не найдена колонка, содержащая 'weight'" or
        "missing columns" in error_message_lower
    )
    # Логируем проверяемое сообщение (начало) и результат
    logging.debug(f"is_column_related_error: Проверка '{error_message[:150]}...' -> {result}") # Ограничим длину для лога
    return result

def get_current_metadata_and_package_info(file_path, root):
    """
    Получает ТОЛЬКО метаданные файла и парсит информацию о пакете из пути.
    Если номер партии или дата партии не найдены, устанавливает is_error=True
    в ВОЗВРАЩАЕМОМ словаре. Не генерирует исключение для этого случая.
    """
    logging.debug(f"Получение metadata/package info (без чтения Excel): {file_path}")
    # Базовый словарь - используется ТОЛЬКО при РЕАЛЬНОМ исключении
    file_info_base = {
        'full_path': file_path,
        'target_folder': os.path.basename(root) if root else 'Unknown',
        'file_name': os.path.basename(file_path),
        'dtflow': datetime.now(),
        'is_error': True,
        'error_message': 'Unknown exception during metadata/path parsing',
        'dt_create': None, 'dt_modified': None, 'size_kb': None,
        'dt_package': None, 'package_num': None,
        'parse_type': 'metadata_only'
    }
    metadata = {}

    try:
        # 1. Получаем метаданные файла
        metadata = get_file_metadata(file_path)

        # 2. Парсим информацию о пакете из пути (БЕЗ генерации исключения при НЕнаходке)
        package_num = None
        dt_package = None
        try:
            relative_path = os.path.relpath(file_path, START_DIR)
            match = PACKAGE_PATTERN.search(relative_path)
            if match:
                package_num_str = match.group(1)
                date_str = match.group(2)
                if package_num_str:
                     package_num = package_num_str
                     try:
                         dt_package = datetime.strptime(date_str, '%d.%m.%Y').date()
                     except ValueError:
                         logging.warning(f"Неверный формат даты пакета в пути: {file_path}. Найдено: {date_str}. Дата не будет установлена.")
            # else: паттерн не найден, останутся None
        except ValueError as path_err:
             logging.error(f"Ошибка получения относительного пути для {file_path}: {path_err}")

        # 3. Собираем РЕЗУЛЬТАТНЫЙ словарь
        result_data = {
            'full_path': file_path,
            'target_folder': os.path.basename(root) if root else 'Unknown',
            'file_name': os.path.basename(file_path),
            'dtflow': datetime.now(),
            'is_error': False, # <--- По умолчанию УСПЕХ
            'error_message': None,
            'dt_create': metadata.get('dt_create'),
            'dt_modified': metadata.get('dt_modified'),
            'size_kb': metadata.get('size_kb'),
            'package_num': package_num, # Может быть None
            'dt_package': dt_package,   # Может быть None
            'parse_type': 'metadata_only'
        }

        # 4. ПРОВЕРКА: Если номер или дата не найдены - устанавливаем ошибку
        if package_num is None or dt_package is None:
             result_data['is_error'] = True
             result_data['error_message'] = "Не удалось выделить номер партии и дату партии из пути."
             logging.warning(f"Установлена ошибка (пакет/дата не найдены/невалидны) для файла: {file_path}")

        # Возвращаем РЕЗУЛЬТАТНЫЙ словарь
        return result_data

    except (ValueError, FileNotFoundError, PermissionError, Exception) as e:
        # Ловим РЕАЛЬНЫЕ ИСКЛЮЧЕНИЯ (ошибки доступа, os.stat)
        error_msg_final = f"{type(e).__name__}: {str(e)}"
        logging.error(f"Итоговая ошибка (исключение) при обработке metadata/path для {file_path}: {error_msg_final}")
        # Заполняем базовый словарь ошибкой
        file_info_base['error_message'] = error_msg_final
        if metadata: file_info_base.update(metadata) # Добавляем метаданные если успели получить
        # Возвращаем БАЗОВЫЙ словарь с is_error=True из-за исключения
        return file_info_base
    
def parse_excel_file(file_path, root):
    """
    Анализирует Excel файл. Если номер партии или дата партии не найдены в пути,
    устанавливает is_error=True и соответствующее сообщение в ВОЗВРАЩАЕМОМ словаре.
    Не генерирует исключение для этого случая.
    """
    metadata = {}
    # Базовый словарь - используется ТОЛЬКО если произойдет РЕАЛЬНОЕ исключение
    file_info_base = {
        'target_folder': os.path.basename(root) if root else 'Unknown',
        'file_name': os.path.basename(file_path),
        'full_path': file_path,
        'dtflow': datetime.now(),
        'is_error': True,
        'error_message': 'Unknown exception during parsing', # Сообщение для реальных исключений
        'dt_create': None, 'dt_modified': None, 'size_kb': None,
        'field_count': 0, 'field_list': None, 'row_count': 0,
        'dt_package': None, 'package_num': None,
        'parse_type': 'full' 
    }
    workbook = None

    try:
        # 1. Получаем метаданные файла -> сохраняем в 'metadata'
        metadata = get_file_metadata(file_path)

        # 2. Читаем Excel
        headers = []
        row_count = 0
        try:
            workbook = load_workbook(filename=file_path, read_only=True, data_only=True)
            # ... (чтение заголовков и row_count ) ...
            sheet = workbook.active
            if sheet.max_row == 0: raise ValueError("Excel файл пустой (нет строк)")
            headers = [cell.value for cell in sheet[1]]
            if not any(headers): raise ValueError("Строка заголовков пуста")
            row_count = sheet.max_row - 1 if sheet.max_row > 0 else 0
        except Exception as openpyxl_err:
            # Оборачиваем реальные ошибки чтения
            raise ValueError(f"Ошибка чтения Excel ({type(openpyxl_err).__name__}): {openpyxl_err}") from openpyxl_err
        finally:
            if workbook: workbook.close()

        # 3. Проверяем обязательные колонки (вызовет ValueError при ошибке)
        check_required_columns(headers)

        # 4. Парсим информацию о пакете из пути (БЕЗ генерации исключения при НЕ находим)
        package_num = None
        dt_package = None
        try:
            relative_path = os.path.relpath(file_path, START_DIR)
            match = PACKAGE_PATTERN.search(relative_path)
            if match:
                package_num_str = match.group(1)
                date_str = match.group(2)
                if package_num_str: # Проверка на пустую группу номера
                     package_num = package_num_str
                     try:
                         # Пытаемся распарсить дату ТОЛЬКО если номер найден
                         dt_package = datetime.strptime(date_str, '%d.%m.%Y').date()
                     except ValueError:
                         # Неверный формат даты - это ошибка, но не критическая, просто дата будет None
                         logging.warning(f"Неверный формат даты пакета в пути: {file_path}. Найдено: {date_str}. Дата не будет установлена.")
                         # dt_package останется None
                # else: номер пустой, package_num останется None
            # else: паттерн не найден, package_num и dt_package останутся None
        except ValueError as path_err:
             # Ловим ТОЛЬКО ошибки от os.path.relpath (редко)
             logging.error(f"Ошибка получения относительного пути для {file_path}: {path_err}")
             # Не прерываем, просто номер/дата будут None

        # 5. Собираем РЕЗУЛЬТАТНЫЙ словарь (даже если парсинг пути не удался)
        result_data = {
            'target_folder': os.path.basename(root) if root else 'Unknown',
            'file_name': os.path.basename(file_path),
            'full_path': file_path,
            'dtflow': datetime.now(),
            'is_error': False, # <--- По умолчанию УСПЕХ
            'error_message': None,
            'dt_create': metadata.get('dt_create'),
            'dt_modified': metadata.get('dt_modified'),
            'size_kb': metadata.get('size_kb'),
            'field_count': len(headers),
            'field_list': ";".join(map(str, filter(None, headers))),
            'row_count': row_count,
            'package_num': package_num, # Может быть None
            'dt_package': dt_package,   # Может быть None
            'parse_type': 'full'
        }

        # 6. ПРОВЕРКА: Если номер или дата не найдены - устанавливаем ошибку
        if package_num is None or dt_package is None:
             result_data['is_error'] = True
             result_data['error_message'] = "Не удалось выделить номер партии и дату партии из пути."
             logging.warning(f"Установлена ошибка (пакет/дата не найдены/невалидны) для файла: {file_path}")

        # Возвращаем РЕЗУЛЬТАТНЫЙ словарь (он может содержать is_error=True)
        return result_data

    except (ValueError, FileNotFoundError, PermissionError, Exception) as e:
        # Этот блок ловит РЕАЛЬНЫЕ ИСКЛЮЧЕНИЯ (ошибки доступа, чтения Excel, проверки колонок)
        error_msg_final = f"{type(e).__name__}: {str(e)}"
        logging.error(f"Итоговая ошибка (исключение) при обработке файла {file_path}: {error_msg_final}")
        # Заполняем базовый словарь ошибкой
        file_info_base['error_message'] = error_msg_final
        # Пытаемся добавить метаданные, если они были получены до исключения или получаемы сейчас
        if metadata: file_info_base.update(metadata)
        elif os.path.exists(file_path):
             try: file_info_base.update(get_file_metadata(file_path))
             except Exception: pass
        # Возвращаем БАЗОВЫЙ словарь с is_error=True из-за исключения
        return file_info_base
    
        # 5. Собираем результат - УСПЕХ
        # Этот блок выполняется только если НИГДЕ выше не было исключений
        file_info_success = {
            **file_info_base, # Берем базовую инфу + метаданные
            'field_count': len(headers),
            'field_list': ";".join(map(str, filter(None, headers))),
            'row_count': row_count,
            'is_error': False,         # Явно ставим False
            'error_message': None,     # Сбрасываем сообщение
            'dt_package': dt_package,  # Записываем результат парсинга (может быть None)
            'package_num': package_num # Записываем результат парсинга (может быть None)
        }
        # logging.info(f"Успешно обработан файл: {file_path}") # Лог успеха
        return file_info_success

    except (ValueError, FileNotFoundError, PermissionError, Exception) as e:
        # Этот блок ловит ВСЕ исключения: из get_metadata, load_workbook,
        # check_columns И те, что мы генерируем в блоке парсинга пути (шаг 4).
        error_msg_final = f"{type(e).__name__}: {str(e)}"
        logging.error(f"Итоговая ошибка обработки файла {file_path}: {error_msg_final}")
        # Заполняем сообщение об ошибке в базовом словаре
        file_info_base['error_message'] = error_msg_final
        # Пытаемся обновить метаданные, если они не были получены до ошибки
    if not metadata and 'metadata' not in locals() and os.path.exists(file_path):
        try:
            metadata_fallback = get_file_metadata(file_path)
            file_info_base.update(metadata_fallback)
        except Exception as meta_err: # Ловим любую ошибку при получении метаданных здесь
            logging.error(f"Не удалось получить метаданные для файла с ошибкой {file_path}: {meta_err}")
    # Возвращаем базовый словарь с is_error=True и error_message
    return file_info_base

async def scan_files_async(start_dir, executor, existing_files_info):
    """
    Асинхронно сканирует директории. Выбирает тип задачи.
    Возвращает список словарей для ВСЕХ обработанных задач (включая ошибки).
    """
    loop = asyncio.get_running_loop()
    tasks_futures = []
    # Обновляем task_map, чтобы хранить путь для логирования ошибок await
    task_map = {} # {future: {'type': 'full'/'metadata_only', 'path': file_path}}
    all_results_data = [] # Будем собирать ВСЕ результаты
    total_files_found = 0
    skipped_known_error_count = 0
    skipped_wrong_extension = 0 # Счетчик пропущенных из-за расширения
    files_for_full_parse = 0
    files_for_metadata_only = 0

    logging.info(f"Начало асинхронного сканирования: {start_dir} (с выбором типа парсинга)")

    if not os.path.isdir(start_dir):
        logging.error(f"Стартовая директория не найдена: {start_dir}")
        return []

    for root, _, files in os.walk(start_dir):
        for file in files:
        
            # 1. Пропускаем временные файлы Excel
            if file.startswith("~$"):
                logging.debug(f"Пропуск временного файла: {os.path.join(root, file)}")
                continue

            # 2. Проверяем расширение ЯВНО (регистронезависимо)
            # ИСПОЛЬЗУЕМ ЭТОТ ВАРИАНТ для .xlsx
            if not file.lower().endswith(".xlsx"):
                 logging.debug(f"Пропуск файла с неверным расширением: {os.path.join(root, file)}")
                 skipped_wrong_extension += 1
                 continue
            
            file_path = os.path.join(root, file)
            total_files_found += 1
            db_info = existing_files_info.get(file_path)
            task_future = None
            task_type = None

            # --- Логика выбора типа задачи (остается как в предыдущем варианте) ---
            if not db_info: # Новый файл -> full
                task_future = loop.run_in_executor(executor, parse_excel_file, file_path, str(root))
                task_type = 'full'
                files_for_full_parse += 1
            else: # Существующий файл
                db_is_error = db_info.get('is_error')
                db_error_msg = db_info.get('error_message')
                if db_is_error:
                    if is_column_related_error(db_error_msg): # Ошибка колонок -> skip
                        skipped_known_error_count += 1
                        continue
                    else: # Другая ошибка -> full
                        task_future = loop.run_in_executor(executor, parse_excel_file, file_path, str(root))
                        task_type = 'full'
                        files_for_full_parse += 1
                else: # Без ошибки -> metadata_only
                    task_future = loop.run_in_executor(executor, get_current_metadata_and_package_info, file_path, str(root))
                    task_type = 'metadata_only'
                    files_for_metadata_only += 1

            if task_future and task_type:
                tasks_futures.append(task_future)
                # Связываем future с типом И ПУТЕМ
                task_map[task_future] = {'type': task_type, 'path': file_path}

    logging.info(f"Всего файлов найдено в директориях (до фильтрации): {total_files_found + skipped_wrong_extension}. " # Обновим лог
                 f"Пропущено (не .xlsx): {skipped_wrong_extension}. "
                 f"Найдено .xlsx файлов для анализа: {total_files_found}. "
                 f"Пропущено (ошибка колонок): {skipped_known_error_count}. "
                 f"Задачи: Полный парсинг={files_for_full_parse}, Только метаданные={files_for_metadata_only}.")
    
    # --- Ожидание и обработка результатов ---
    processed_count = 0
    for future in asyncio.as_completed(tasks_futures):
        # Получаем инфо о задаче ДО await, на случай ошибки await
        task_info = task_map.get(future)
        task_type = task_info['type'] if task_info else 'unknown'
        task_path = task_info['path'] if task_info else 'unknown_path'
        processed_count += 1

        try:
            result_data = await future # Получаем результат (словарь)
            # Добавляем инфо (на всякий случай)
            result_data.setdefault('parse_type', task_type)
            result_data.setdefault('full_path', task_path)

            # --- ИЗМЕНЕНИЕ: Добавляем ВСЕ результаты в список ---
            all_results_data.append(result_data)

            # Логируем только если была ошибка ВНУТРИ задачи
            if result_data.get('is_error'):
                logging.warning(f"Задача для {result_data.get('full_path')} (тип: {task_type}) завершилась с ошибкой ВНУТРИ: {result_data.get('error_message')[:150]}...") # Ограничим длину

        except Exception as e:
            # Ошибка при ПОЛУЧЕНИИ результата из future (await future)
            # Используем task_path и task_type, полученные до await
            logging.error(f"Критическая ошибка при ПОЛУЧЕНИИ результата из future для файла {task_path} (тип {task_type}): {e}", exc_info=True)
            # --- ИЗМЕНЕНИЕ: Создаем запись об этой ошибке, чтобы она попала в БД ---
            error_result = {
                'full_path': task_path,
                'target_folder': os.path.basename(os.path.dirname(task_path)) if task_path != 'unknown_path' else 'Unknown',
                'file_name': os.path.basename(task_path) if task_path != 'unknown_path' else 'Unknown',
                'dtflow': datetime.now(),
                'is_error': True,
                'error_message': f"Критическая ошибка executor/await: {type(e).__name__}: {e}",
                'parse_type': task_type,
                'dt_create': None, 'dt_modified': None, 'size_kb': None, # Метаданные неизвестны
                'field_count': None, 'field_list': None, 'row_count': None, # Содержимое неизвестно
                'dt_package': None, 'package_num': None
            }
            all_results_data.append(error_result) # Добавляем словарь с ошибкой

        # Логируем прогресс
        total_tasks = len(tasks_futures)
        if processed_count % 100 == 0 or processed_count == total_tasks:
             logging.info(f"Обработано задач: {processed_count}/{total_tasks}...")

    logging.info(f"Обработка задач завершена. Собрано результатов (включая ошибки): {len(all_results_data)} "
                 f"(из {len(tasks_futures)} задач). Пропущено (ошибка колонок): {skipped_known_error_count}.")
    # --- ИЗМЕНЕНИЕ: Возвращаем ВСЕ результаты ---
    return all_results_data

def update_database(processed_files_data, existing_files_info):
    """
    Обновляет базу данных. Обрабатывает ВСЕ результаты из processed_files_data,
    включая те, что содержат is_error=True. Корректно обрабатывает
    добавление/обновление записей с ошибками.
    """
    if not processed_files_data:
        logging.info("Нет данных для обработки в базе данных.")
        return

    logging.info("Подключение к базе данных для обновления...")
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        logging.info("Соединение с БД установлено.")
        with conn.cursor() as cursor:

            logging.debug(f"Получено {len(processed_files_data)} результатов для обработки в БД.")
            logging.debug(f"Используется {len(existing_files_info)} предзагруженных записей для сравнения.")

            new_records_to_insert = []
            records_to_update = []
            skipped_no_change = 0

            for file_data in processed_files_data: # Обрабатываем все результаты
                full_path = file_data.get('full_path')
                if not full_path:
                    logging.error(f"Пропуск записи без full_path: {file_data}")
                    continue

                db_info = existing_files_info.get(full_path)
                current_is_error = file_data.get('is_error', False)
                current_error_msg = file_data.get('error_message')
                file_dt_modified = file_data.get('dt_modified')

                if not db_info:
                    # --- Случай 1: Новый файл (вставляем всегда) ---
                    logging.debug(f"Файл '{full_path}' будет добавлен как новый (is_error={current_is_error}).")
                    new_records_to_insert.append(file_data)
                else:
                    # --- Случай 2: Существующий файл ---
                    db_dt_modified = db_info.get('dt_modified')
                    db_is_error = db_info.get('is_error')
                    db_error_msg = db_info.get('error_message')

                    needs_update = False
                    update_reason = "N/A"

                    # --- ИЗМЕНЕНИЕ ЛОГИКИ: Проверяем необходимость обновления ---
                    # 1. Изменился статус ошибки?
                    if current_is_error != db_is_error:
                        needs_update = True
                        update_reason = f"изменение статуса ошибки (БД: {db_is_error}, тек: {current_is_error})"
                    # 2. Ошибка не изменилась, но текст ошибки другой? (и ошибка есть)
                    elif current_is_error and db_is_error and current_error_msg != db_error_msg:
                        needs_update = True
                        update_reason = "изменение текста ошибки"
                    # 3. Статус ошибки не изменился, но файл новее?
                    elif file_dt_modified is not None and db_dt_modified is not None and file_dt_modified > db_dt_modified:
                        needs_update = True
                        update_reason = "файл новее"
                    # 4. Статус ошибки не изменился, но дата в базе была NULL?
                    elif file_dt_modified is not None and db_dt_modified is None:
                         needs_update = True
                         update_reason = "dt_modified в базе было NULL"

                    # Дополнительная проверка: если пришел УСПЕШНЫЙ результат ('is_error': False),
                    # а в базе БЫЛА ошибка (любая, включая колонки, т.к. пропущенные сюда не дойдут),
                    # то ТОЖЕ нужно обновить, чтобы сбросить флаг ошибки.
                    if not current_is_error and db_is_error:
                        needs_update = True
                        update_reason = "ошибка исправлена (ранее была в БД)"


                    if needs_update:
                        logging.debug(f"Файл '{full_path}' будет обновлен. Причина: {update_reason}.")
                        records_to_update.append(file_data) # file_data содержит актуальные is_error/error_message
                    else:
                        logging.debug(f"Файл '{full_path}' не требует обновления (is_error={current_is_error}, дата={file_dt_modified} vs {db_dt_modified}).")
                        skipped_no_change += 1

            # --- Вставка новых записей ---
            if new_records_to_insert:
                logging.info(f"Подготовка к вставке {len(new_records_to_insert)} новых записей...")
                # Колонки для вставки (всегда берем все возможные)
                columns = [
                    'target_folder', 'file_name', 'full_path', 'dt_create', 'dt_modified',
                    'size_kb', 'dtflow', 'field_count', 'field_list', 'row_count',
                    'is_error', 'error_message', 'dt_package', 'package_num'
                ]
                # Отбираем только те, что реально есть в первом словаре (для универсальности)
                cols_to_insert = [col for col in columns if col in new_records_to_insert[0]]
                # Формируем SQL
                cols_sql = sql.SQL(', ').join(map(sql.Identifier, cols_to_insert))
                vals_sql = sql.SQL(', ').join([sql.Placeholder()] * len(cols_to_insert))
                insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    sql.Identifier(*TABLE_NAME.split('.')), cols_sql, vals_sql
                )
                # Готовим данные (используем get с default=None)
                data_to_insert = [
                    tuple(file.get(col) for col in cols_to_insert)
                    for file in new_records_to_insert
                ]
                try:
                    cursor.executemany(insert_query, data_to_insert)
                    logging.info(f"Успешно добавлено {cursor.rowcount} новых записей.")
                except Exception as insert_err:
                    logging.error(f"Ошибка при пакетной вставке: {insert_err}")
                    conn.rollback()
                    raise

            # --- Обновление существующих записей ---
            if records_to_update:
                logging.info(f"Подготовка к обновлению {len(records_to_update)} записей...")
                # Определяем базовые колонки и колонки полного парсинга
                base_update_cols = ['dt_modified', 'dt_create', 'size_kb',
                                    'target_folder', 'file_name',
                                    'dt_package', 'package_num',
                                    'is_error', 'error_message'] # Важно обновлять статус ошибки
                full_parse_cols = ['field_count', 'field_list', 'row_count']

                update_count = 0
                errors_in_update = 0
                for file in records_to_update:
                    current_path = file['full_path']
                    current_parse_type = file.get('parse_type')
                    current_is_error = file.get('is_error')

                    # Определяем набор колонок для SET
                    cols_to_set = list(base_update_cols)
                    # Если парсинг был полным И НЕ было ошибки -> добавляем колонки из Excel
                    if current_parse_type == 'full' and not current_is_error:
                        cols_to_set.extend(full_parse_cols)
                    # Если парсинг был только метаданных И НЕ было ошибки -> ничего не добавляем
                    # Если БЫЛА ошибка (любого типа парсинга) -> обновляем только базовые + статус ошибки

                    # Формируем SET часть + сброс dt_processed
                    set_sql_parts = [sql.SQL("{} = %s").format(sql.Identifier(col)) for col in cols_to_set]
                    set_sql_parts.append(sql.SQL("dt_processed = NULL")) # Сбрасываем всегда при обновлении

                    # Формируем значения
                    values_to_update = tuple(file.get(col) for col in cols_to_set) + (current_path,)

                    # Выполняем запрос
                    try:
                        update_query = sql.SQL("UPDATE {} SET {} WHERE full_path = %s").format(
                            sql.Identifier(*TABLE_NAME.split('.')),
                            sql.SQL(', ').join(set_sql_parts)
                        )
                        cursor.execute(update_query, values_to_update)
                        update_count += cursor.rowcount
                    except Exception as update_err:
                        errors_in_update += 1
                        logging.error(f"Ошибка при обновлении ({current_parse_type}, is_error={current_is_error}) для {current_path}: {update_err}")

                logging.info(f"Попытка обновления {len(records_to_update)} записей. Обновлено строк: {update_count}. Ошибок: {errors_in_update}.")
                if errors_in_update > 0:
                     logging.warning("При обновлении записей возникли ошибки.")

            conn.commit()
            logging.info("Изменения успешно сохранены в базе данных.")

    except psycopg2.OperationalError as e:
         logging.error(f"Ошибка подключения к базе данных: {e}")
    except Exception as e:
        logging.error(f"Ошибка при работе с базой данных: {str(e)}", exc_info=True)
        if conn: conn.rollback()
    finally:
        if conn:
            conn.close()
            logging.info("Соединение с БД закрыто.")

async def main():
    """Основная асинхронная функция"""
    start_time = datetime.now()
    logging.info(f"=== Начало асинхронной обработки ===")
    logging.info(f"Стартовая директория: {START_DIR}")
    logging.info(f"Таблица реестра: {TABLE_NAME}")
    logging.info(f"Макс. потоков для сканирования: {MAX_WORKERS}")

    existing_files_info = {} # Словарь для хранения данных из БД
    conn = None
    try:
        # --- Шаг 1: Предварительная загрузка данных из БД ---
        logging.info("Предварительная загрузка статусов файлов из базы данных...")
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            # Загружаем нужные поля для всех записей
            cursor.execute(
                sql.SQL("SELECT full_path, dt_modified, is_error, error_message FROM {}")
                .format(sql.Identifier(*TABLE_NAME.split('.')))
            )
            # Сохраняем в удобном формате
            for row in cursor.fetchall():
                full_path, dt_modified, is_error, error_message = row
                existing_files_info[full_path] = {
                    'dt_modified': dt_modified,
                    'is_error': is_error,
                    'error_message': error_message
                }
            logging.info(f"Загружено {len(existing_files_info)} записей из реестра.")
        conn.close() # Закрываем соединение после чтения
        conn = None # Сбрасываем, чтобы не закрывать повторно в finally

        # --- Шаг 2: Асинхронное сканирование с учетом предзагруженных данных ---
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Получаем ВСЕ результаты
            all_results_data = await scan_files_async(START_DIR, executor, existing_files_info)

            # --- Шаг 3: Обновление базы данных ---
            # --- Проверяем, есть ли ВООБЩЕ результаты ---
            if all_results_data or os.getenv('FORCE_DB_UPDATE') == '1':
                # Передаем все результаты в update_database
                update_database(all_results_data, existing_files_info)
            else:
                 # Эта ветка теперь маловероятна, только если ВООБЩЕ не найдено файлов
                 logging.info("Не найдено файлов для обработки или все пропущены (ошибка колонок), обновление БД пропускается.")

    except psycopg2.OperationalError as db_err:
        logging.error(f"Ошибка подключения к БД при предварительной загрузке: {db_err}")
    except Exception as e:
        logging.critical(f"Критическая ошибка в процессе выполнения main: {str(e)}", exc_info=True)
    finally:
        if conn: # Если соединение осталось открытым из-за ошибки до close()
             conn.close()
             logging.warning("Соединение с БД было принудительно закрыто в finally.")
        # ... (логирование времени выполнения) ...
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logging.info(f"=== Обработка завершена за {duration:.2f} сек ===")

if __name__ == "__main__":
    asyncio.run(main())