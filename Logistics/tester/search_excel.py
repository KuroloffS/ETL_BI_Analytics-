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
TABLE_NAME = 'public.excel_registry'
FILE_PATTERN = re.compile(r".*\.xlsx$", re.IGNORECASE)
PACKAGE_PATTERN = re.compile(r"-\s*(\d+).*?\((\d{2}\.\d{2}\.\d{4})\)")
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

# ИСПРАВЛЕННАЯ ФУНКЦИЯ
def parse_excel_file(file_path, root):
    """
    Анализирует Excel файл и возвращает данные для реестра.
    Эта функция СИНХРОННАЯ и будет запускаться в ThreadPoolExecutor.
    Использует try...finally для закрытия workbook.
    """
    metadata = {}
    file_info_base = {
        'target_folder': os.path.basename(root) if root else 'Unknown',
        'file_name': os.path.basename(file_path),
        'full_path': file_path,
        'dtflow': datetime.now(),
        'is_error': True,
        'error_message': 'Unknown error during parsing initiation',
        'dt_create': None, 'dt_modified': None, 'size_kb': None,
        'field_count': 0, 'field_list': None, 'row_count': 0,
        'dt_package': None, 'package_num': None
    }
    workbook = None  # Инициализируем workbook как None

    try:
        # 1. Получаем метаданные файла
        metadata = get_file_metadata(file_path)
        file_info_base.update(metadata)

        # 2. Читаем Excel
        headers = []
        row_count = 0
        try:
            # Открываем workbook БЕЗ 'with'
            workbook = load_workbook(filename=file_path, read_only=True, data_only=True)
            sheet = workbook.active
            if sheet.max_row == 0:
                raise ValueError("Excel файл пустой (нет строк)")
            headers = [cell.value for cell in sheet[1]]
            if not any(headers):
                raise ValueError("Строка заголовков пуста или не найдена в файле Excel")
            row_count = sheet.max_row - 1 if sheet.max_row > 0 else 0
        except Exception as openpyxl_err:
            # Оборачиваем ошибку openpyxl для консистентности
            raise ValueError(f"Ошибка чтения Excel файла ({type(openpyxl_err).__name__}): {openpyxl_err}") from openpyxl_err
        finally:
            # Гарантированно закрываем workbook, если он был успешно открыт
            if workbook:
                workbook.close()
                # logging.debug(f"Workbook closed for: {file_path}") # Можно раскомментировать для отладки

        # 3. Проверяем обязательные колонки
        check_required_columns(headers)

        # 4. Парсим информацию о пакете из пути
        dt_package = package_num = None
        try:
            relative_path = os.path.relpath(file_path, START_DIR)
            match = PACKAGE_PATTERN.search(relative_path)
            if match:
                package_num = match.group(1)
                try:
                    dt_package = datetime.strptime(match.group(2), '%d.%m.%Y').date()
                except ValueError:
                    logging.warning(f"Неверный формат даты в пути файла: {file_path}. Найдено: {match.group(2)}")
        except ValueError as path_err: # Ошибка может быть в os.path.relpath если START_DIR некорректен
             logging.warning(f"Ошибка при обработке пути для извлечения пакета: {file_path}, {path_err}")


        # 5. Собираем результат - УСПЕХ
        file_info = {
            **file_info_base,
            'field_count': len(headers),
            'field_list': ";".join(map(str, filter(None, headers))),
            'row_count': row_count,
            'is_error': False,
            'error_message': None,
            'dt_package': dt_package,
            'package_num': package_num
        }
        return file_info

    except (ValueError, FileNotFoundError, PermissionError, Exception) as e:
        # Ловим все ошибки, включая ValueError от get_file_metadata, check_required_columns и чтения Excel
        error_msg = f"Ошибка обработки файла {file_path}: {type(e).__name__} - {str(e)}"
        logging.error(error_msg)
        # Обновляем сообщение об ошибке в базовом словаре
        file_info_base['error_message'] = f"{type(e).__name__}: {str(e)}"
        # Пытаемся обновить метаданные, если они еще не были получены до ошибки
        # (Например, если ошибка была при чтении Excel или проверке колонок)
        if not metadata and 'metadata' not in locals() and os.path.exists(file_path):
             try:
                 metadata_fallback = get_file_metadata(file_path)
                 file_info_base.update(metadata_fallback)
             except ValueError as meta_err:
                 logging.error(f"Не удалось получить метаданные для файла с ошибкой {file_path}: {meta_err}")

        return file_info_base


async def scan_files_async(start_dir, executor):
    """
    Асинхронно сканирует директории и запускает парсинг файлов в ThreadPoolExecutor.
    Возвращает список данных успешно обработанных файлов.
    """
    loop = asyncio.get_running_loop()
    tasks = []
    valid_files_count = 0
    processed_files_data = []
    total_files_found = 0

    logging.info(f"Начало асинхронного сканирования директории: {start_dir} с {MAX_WORKERS} воркерами")

    if not os.path.isdir(start_dir):
        logging.error(f"Стартовая директория не найдена или не является директорией: {start_dir}")
        return []

    for root, _, files in os.walk(start_dir):
        # logging.debug(f"Сканирование папки: {root}") # Можно раскомментировать для отладки
        for file in files:
            if file.startswith("~$") or not FILE_PATTERN.match(file):
                continue

            file_path = os.path.join(root, file)
            total_files_found += 1
            task = loop.run_in_executor(executor, parse_excel_file, file_path, str(root))
            tasks.append(task)

    logging.info(f"Найдено {total_files_found} потенциальных .xlsx файлов. Запуск обработки...")

    processed_count = 0
    for future in asyncio.as_completed(tasks):
        try:
            file_data = await future
            processed_count += 1
            if not file_data['is_error']:
                processed_files_data.append(file_data)
                valid_files_count += 1
                # logging.debug(f"Успешно обработан файл: {file_data['full_path']}") # Успех логируется в parse_excel_file
            # else: # Ошибки логируются в parse_excel_file

            if processed_count % 100 == 0 or processed_count == total_files_found : # Логируем прогресс
                 logging.info(f"Обработано {processed_count}/{total_files_found} файлов...")

        except Exception as e:
            logging.error(f"Критическая ошибка при получении результата из потока: {e}", exc_info=True)

    logging.info(f"Сканирование и обработка завершены. Валидных файлов для БД: {valid_files_count} из {total_files_found} найденных.")
    return processed_files_data


# СКОРРЕКТИРОВАННАЯ ФУНКЦИЯ (убрано создание индекса)
def update_database(files_data):
    """Обновляет базу данных (синхронная функция)"""
    if not files_data:
        logging.info("Нет валидных файлов для обновления базы данных.")
        return

    logging.info("Подключение к базе данных для обновления...")
    conn = None # Инициализируем для finally
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        logging.info("Соединение с БД установлено.")
        with conn.cursor() as cursor:

            # --- Код создания индекса УБРАН ---
            # logging.info(f"Проверка наличия индекса на {TABLE_NAME}(full_path)...") # Можно оставить для информации

            # Получаем текущее состояние реестра
            logging.debug("Получение существующих записей из базы данных...")
            try:
                cursor.execute(
                    sql.SQL("SELECT full_path, dt_modified FROM {}")
                    .format(sql.Identifier(*TABLE_NAME.split('.')))
                )
                existing_files = {row[0]: row[1] for row in cursor.fetchall()}
                logging.debug(f"Загружено {len(existing_files)} существующих записей.")
            except Exception as e:
                logging.error(f"Ошибка при получении существующих записей: {e}")
                raise # Прерываем выполнение, если не можем получить состояние

            # Разделяем файлы на новые и требующие обновления
            new_files = []
            files_to_update = []
            for file_data in files_data: # Только валидные файлы
                full_path = file_data['full_path']
                db_dt_modified = existing_files.get(full_path)
                file_dt_modified = file_data.get('dt_modified')

                if full_path not in existing_files:
                    logging.debug(f"Файл '{full_path}' будет добавлен как новый.")
                    new_files.append(file_data)
                else:
                    update_reason = None
                    if db_dt_modified is None and file_dt_modified is not None:
                         update_reason = "dt_modified в базе было NULL, а в файле есть дата"
                    elif file_dt_modified is not None and db_dt_modified is not None and file_dt_modified > db_dt_modified:
                         update_reason = f"файл новее (Файл: {file_dt_modified}, База: {db_dt_modified})"

                    if update_reason:
                        logging.debug(f"Файл '{full_path}' будет обновлен. Причина: {update_reason}.")
                        files_to_update.append(file_data)

            # Вставка новых файлов
            if new_files:
                logging.info(f"Подготовка к вставке {len(new_files)} новых записей...")
                columns = list(new_files[0].keys())
                cols_sql = sql.SQL(', ').join(map(sql.Identifier, columns))
                vals_sql = sql.SQL(', ').join([sql.Placeholder()] * len(columns))
                insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    sql.Identifier(*TABLE_NAME.split('.')), cols_sql, vals_sql
                )
                data_to_insert = [tuple(file.get(col) for col in columns) for file in new_files]
                try:
                    cursor.executemany(insert_query, data_to_insert)
                    logging.info(f"Успешно добавлено {cursor.rowcount} новых записей.")
                except Exception as insert_err:
                    logging.error(f"Ошибка при пакетной вставке новых записей: {insert_err}")
                    conn.rollback() # Откатываем транзакцию при ошибке вставки
                    raise # Передаем ошибку дальше

            # Обновление существующих файлов
            if files_to_update:
                logging.info(f"Подготовка к обновлению {len(files_to_update)} записей...")
                update_cols = [
                    'dt_modified', 'dt_create', 'size_kb', 'field_count',
                    'field_list', 'row_count', 'target_folder', 'file_name',
                    'dt_package', 'package_num'
                ]
                set_sql_parts = [sql.SQL("{} = %s").format(sql.Identifier(col)) for col in update_cols]
                set_sql_parts.extend([
                    sql.SQL("dt_processed = NULL"),
                    sql.SQL("is_error = FALSE"),
                    sql.SQL("error_message = NULL")
                ])
                update_query = sql.SQL("UPDATE {} SET {} WHERE full_path = %s").format(
                    sql.Identifier(*TABLE_NAME.split('.')),
                    sql.SQL(', ').join(set_sql_parts)
                )
                update_count = 0
                errors_in_update = 0
                for file in files_to_update:
                     values_to_update = tuple(file.get(col) for col in update_cols) + (file['full_path'],)
                     try:
                         cursor.execute(update_query, values_to_update)
                         if cursor.rowcount > 0:
                             update_count += 1
                             # logging.debug(f"Запись для '{file['full_path']}' обновлена.")
                         else: # Файл был в existing_files, но UPDATE не нашел строку (редко, но возможно)
                             logging.warning(f"Не удалось обновить запись для '{file['full_path']}' (возможно, удалена?).")
                     except Exception as update_err:
                         errors_in_update += 1
                         logging.error(f"Ошибка при обновлении записи для {file['full_path']}: {update_err}")
                         # Решаем: откатить все или пропустить эту запись?
                         # Пока просто логируем и считаем ошибки. Можно добавить conn.rollback() здесь,
                         # если одна ошибка обновления должна отменить все обновления.

                logging.info(f"Попытка обновления {len(files_to_update)} записей. Успешно обновлено: {update_count}. Ошибок: {errors_in_update}.")
                if errors_in_update > 0:
                     logging.warning("При обновлении записей возникли ошибки. Транзакция может быть неполной.")
                     # Здесь можно решить откатить ли транзакцию: conn.rollback(); raise Exception(...)

            conn.commit() # Коммитим только если не было явного rollback
            logging.info("Изменения успешно сохранены в базе данных.")

    except psycopg2.OperationalError as e:
         logging.error(f"Ошибка подключения к базе данных: {e}")
         # Не передаем ошибку дальше, чтобы сработало finally в main
    except Exception as e:
        logging.error(f"Ошибка при работе с базой данных: {str(e)}", exc_info=True)
        if conn:
            conn.rollback() # Откатываем транзакцию при любой другой ошибке БД
        # Не передаем ошибку дальше
    finally:
        if conn:
            conn.close() # Гарантированно закрываем соединение
            logging.info("Соединение с БД закрыто.")


async def main():
    """Основная асинхронная функция"""
    start_time = datetime.now()
    logging.info(f"=== Начало асинхронной обработки ===")
    logging.info(f"Стартовая директория: {START_DIR}")
    logging.info(f"Таблица реестра: {TABLE_NAME}")
    logging.info(f"Макс. потоков для сканирования: {MAX_WORKERS}")

    # Используем 'with' для ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        try:
            # 1. Асинхронно сканируем файлы
            valid_files = await scan_files_async(START_DIR, executor)

            # 2. Синхронно обновляем базу данных
            if valid_files or os.getenv('FORCE_DB_UPDATE') == '1': # Добавим возможность принудительного запуска, если нужно
                update_database(valid_files)
            else:
                 logging.info("Не найдено валидных файлов и нет принудительного флага, обновление БД пропускается.")

        except Exception as e:
            logging.critical(f"Критическая ошибка в процессе выполнения main: {str(e)}", exc_info=True)
        finally:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logging.info(f"=== Обработка завершена за {duration:.2f} сек ===")

if __name__ == "__main__":
    asyncio.run(main())