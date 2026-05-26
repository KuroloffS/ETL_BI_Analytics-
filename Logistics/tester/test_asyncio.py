import os
import re
import psycopg2
from psycopg2 import sql
from datetime import datetime
from openpyxl import load_workbook
from dotenv import load_dotenv
import logging

# Настройка логирования (установите DEBUG для детальной информации)
logging.basicConfig(
    level=logging.INFO, # Измените на logging.DEBUG для подробного лога
    format="%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s", # Добавил имя функции
    handlers=[
        logging.FileHandler("excel_registry.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Загрузка переменных окружения
load_dotenv()

# Конфигурация
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD')
}

START_DIR = r'\\10.1.19.245\C2M Logistics\2025\CAINIAO' # Убедитесь, что путь доступен
TABLE_NAME = 'public.excel_registry'
FILE_PATTERN = re.compile(r".*\.xlsx$", re.IGNORECASE)
# Убедитесь, что шаблон точно соответствует структуре пути
PACKAGE_PATTERN = re.compile(r"-\s*(\d+).*?\((\d{2}\.\d{2}\.\d{4})\)")
REQUIRED_COLUMNS = ["cartonid", "itemid", "masterno", "ordercode",
                   "consigneecountry", "service", "danger_type"]
REQUIRED_COLUMNS_SET = set(REQUIRED_COLUMNS) # Используем множество для быстрой проверки

def check_required_columns(headers):
    """Проверяет наличие обязательных колонок в файле Excel"""
    if not headers: # Добавим проверку на пустые заголовки
        raise ValueError("Файл не содержит заголовков (пустая первая строка).")

    headers_lower_set = {str(h).strip().lower() for h in headers if h is not None} # Удаляем пробелы по краям
    missing = list(REQUIRED_COLUMNS_SET - headers_lower_set) # Элементы в required_set, которых нет в headers_lower_set

    # Проверка наличия колонки со словом 'weight'
    weight_present = any("weight" in col for col in headers_lower_set)

    if missing:
        # Сортируем для единообразия вывода
        raise ValueError(f"Отсутствуют обязательные колонки: {', '.join(sorted(missing))}")
    if not weight_present:
        raise ValueError("Не найдена колонка, содержащая 'weight'")
    logging.debug("Проверка колонок пройдена успешно.") # Лог успеха

def get_file_metadata(file_path):
    """Получает метаданные файла"""
    try:
        logging.debug(f"Получение метаданных для: {file_path}")
        file_stat = os.stat(file_path)
        metadata = {
            'dt_create': datetime.fromtimestamp(file_stat.st_ctime),
            'dt_modified': datetime.fromtimestamp(file_stat.st_mtime),
            'size_kb': file_stat.st_size // 1024
        }
        logging.debug(f"Метаданные получены: {metadata}")
        return metadata
    except FileNotFoundError:
        logging.error(f"Файл не найден при получении метаданных: {file_path}")
        raise ValueError(f"Файл не найден: {file_path}")
    except PermissionError:
        logging.error(f"Ошибка доступа при получении метаданных: {file_path}")
        raise ValueError(f"Ошибка доступа к файлу: {file_path}")
    except Exception as e:
        logging.error(f"Неожиданная ошибка получения метаданных для {file_path}: {str(e)}")
        raise ValueError(f"Ошибка получения метаданных файла: {str(e)}")

def parse_excel_file(file_path, root):
    """Анализирует Excel файл и возвращает данные для реестра"""
    logging.debug(f"Начало парсинга файла: {file_path}")
    metadata = {}
    try:
        # 1. Получаем метаданные файла (может выбросить ValueError)
        metadata = get_file_metadata(file_path)

        # 2. Читаем Excel
        workbook = None # Инициализируем
        try:
            workbook = load_workbook(filename=file_path, read_only=True, data_only=True)
            sheet = workbook.active
            if sheet.max_row == 0: # Проверка на совсем пустой лист
                 raise ValueError("Excel файл пустой (нет строк)")
            # Первая строка - заголовки. Убедимся, что она не пустая
            headers = [cell.value for cell in sheet[1]]
            if not any(headers): # Если все ячейки первой строки пустые
                 raise ValueError("Строка заголовков пуста или не найдена в файле Excel")

            row_count = sheet.max_row - 1 if sheet.max_row > 0 else 0 # Вычитаем заголовок, если он есть
            logging.debug(f"Файл '{os.path.basename(file_path)}': Найдено заголовков: {len(headers)}, строк данных: {row_count}")
        finally:
             if workbook:
                 workbook.close() # Гарантированно закрываем файл

        # 3. Проверяем обязательные колонки (может выбросить ValueError)
        check_required_columns(headers) # Передаем оригинальные заголовки

        # 4. Парсим информацию о пакете из пути
        dt_package = package_num = None
        relative_path = os.path.relpath(file_path, START_DIR) # Используем относительный путь для поиска паттерна
        match = PACKAGE_PATTERN.search(relative_path) # Ищем в относительном пути
        if match:
            package_num = match.group(1)
            try:
                dt_package = datetime.strptime(match.group(2), '%d.%m.%Y').date()
                logging.debug(f"Из пути извлечено: package_num={package_num}, dt_package={dt_package}")
            except ValueError:
                logging.warning(f"Неверный формат даты в пути файла: {file_path}. Найдено: {match.group(2)}")
        else:
             logging.debug(f"Паттерн номера/даты пакета не найден в пути: {relative_path}")


        # 5. Собираем результат
        file_info = {
            'target_folder': os.path.basename(root),
            'file_name': os.path.basename(file_path),
            'full_path': file_path, # Сохраняем полный путь как уникальный идентификатор
            'dt_create': metadata['dt_create'],
            'dt_modified': metadata['dt_modified'],
            'size_kb': metadata['size_kb'],
            'dtflow': datetime.now(), # Время обработки скриптом
            'field_count': len(headers),
            'field_list': ";".join(map(str, filter(None, headers))), # Собираем непустые заголовки
            'row_count': row_count,
            'is_error': False,
            'error_message': None,
            'dt_package': dt_package,
            'package_num': package_num
        }
        logging.info(f"Успешно обработан файл: {file_path}")
        return file_info

    except (ValueError, FileNotFoundError, PermissionError, Exception) as e:
        # Ловим все ошибки, включая ValueError от get_file_metadata и check_required_columns
        error_msg = f"Ошибка обработки файла {file_path}: {str(e)}"
        logging.error(error_msg)
        # Пытаемся получить метаданные, если еще не получены или если ошибка произошла позже
        if not metadata and os.path.exists(file_path):
            try:
                 metadata = get_file_metadata(file_path)
            except ValueError as meta_err:
                 logging.error(f"Не удалось получить метаданные для файла с ошибкой {file_path}: {meta_err}")


        return {
            'target_folder': os.path.basename(root) if 'root' in locals() else 'Unknown', # Если root не определен
            'file_name': os.path.basename(file_path),
            'full_path': file_path,
            'dt_create': metadata.get('dt_create'),
            'dt_modified': metadata.get('dt_modified'),
            'size_kb': metadata.get('size_kb'),
            'dtflow': datetime.now(),
            'field_count': 0,
            'field_list': None,
            'row_count': 0,
            'is_error': True,
            'error_message': str(e), # Записываем текст ошибки
            'dt_package': None,
            'package_num': None
        }

def scan_files(start_dir):
    """Сканирует директории и возвращает список данных успешно обработанных файлов"""
    processed_files_data = []
    logging.info(f"Начало сканирования директории: {start_dir}")

    if not os.path.isdir(start_dir):
        logging.error(f"Стартовая директория не найдена или не является директорией: {start_dir}")
        return []

    for root, _, files in os.walk(start_dir):
        logging.debug(f"Сканирование папки: {root}")
        for file in files:
            # Игнорируем временные файлы Excel и не-xlsx файлы
            if file.startswith("~$") or not FILE_PATTERN.match(file):
                logging.debug(f"Пропуск файла: {file}")
                continue

            file_path = os.path.join(root, file)
            logging.debug(f"Обнаружен потенциальный файл: {file_path}")

            # Парсим файл и получаем его данные или информацию об ошибке
            file_data = parse_excel_file(file_path, root)

            # Добавляем только успешно обработанные файлы (для которых is_error=False)
            # Файлы с ошибками парсинга логируются в parse_excel_file, но не передаются в БД для обновления/вставки
            if not file_data['is_error']:
                processed_files_data.append(file_data)
            # else: # Можно добавить логику для записи ошибок в БД, если нужно
            #    log_error_to_db(file_data) # Например

    logging.info(f"Сканирование завершено. Найдено валидных файлов для обработки: {len(processed_files_data)}")
    return processed_files_data

def update_database(files_data):
    """Обновляет базу данных на основе списка успешно обработанных файлов."""
    if not files_data:
        logging.info("Нет валидных файлов для обновления базы данных.")
        return

    logging.info("Подключение к базе данных...")
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            logging.info("Соединение с БД установлено.")
            with conn.cursor() as cursor:
                
                # Получаем текущее состояние реестра (только нужные поля)
                logging.debug("Получение существующих записей из базы данных...")
                cursor.execute(
                    sql.SQL("SELECT full_path, dt_modified FROM {}")
                    .format(sql.Identifier(*TABLE_NAME.split('.')))
                )
                existing_files = {row[0]: row[1] for row in cursor.fetchall()}
                logging.debug(f"Загружено {len(existing_files)} существующих записей.")

                # Разделяем файлы на новые и требующие обновления
                new_files = []
                files_to_update = []

                for file_data in files_data: # files_data содержит только успешно обработанные файлы
                    full_path = file_data['full_path']
                    db_dt_modified = existing_files.get(full_path) # Получаем dt_modified из базы (или None)

                    if full_path not in existing_files:
                        # Файла нет в базе - добавляем как новый
                        logging.debug(f"Файл '{full_path}' будет добавлен как новый.")
                        new_files.append(file_data)
                    else:
                        # Файл есть в базе, проверяем нужно ли обновлять
                        file_dt_modified = file_data['dt_modified']
                        update_reason = None
                        # Явно проверяем оба условия для логирования
                        if db_dt_modified is None:
                            update_reason = "dt_modified в базе = NULL"
                        # Используемaware datetime comparison если типы разные (хотя psycopg2 обычно возвращает aware)
                        # Но для простоты и если таймзоны не важны, прямое сравнение должно работать
                        elif file_dt_modified and db_dt_modified and file_dt_modified > db_dt_modified:
                             update_reason = f"файл новее (Файл: {file_dt_modified}, База: {db_dt_modified})"
                        # Добавим сравнение с учетом возможного None от файла, хотя metadata должна его содержать
                        elif file_dt_modified and not db_dt_modified:
                             update_reason = "dt_modified в базе было NULL, а в файле появилось" # Маловероятно, но для полноты

                        if update_reason:
                            logging.debug(f"Файл '{full_path}' будет обновлен. Причина: {update_reason}.")
                            files_to_update.append(file_data)
                        else:
                            # Логируем только если дата не изменилась или не NULL
                            if db_dt_modified is not None:
                                logging.debug(f"Файл '{full_path}' не требует обновления (Файл: {file_dt_modified}, База: {db_dt_modified}).")
                            # Если в базе NULL и в файле None (ошибка метаданных?), тоже не обновляем, но это странно

                # Вставляем новые файлы
                if new_files:
                    logging.info(f"Подготовка к вставке {len(new_files)} новых записей...")
                    # Определяем колонки на основе первого файла (они должны быть одинаковы)
                    columns = list(new_files[0].keys())
                    # Убираем dtflow если он генерируется БД (если нет, оставляем)
                    # columns.remove('dtflow') # Пример, если dtflow имеет DEFAULT now() в БД
                    cols_sql = sql.SQL(', ').join(map(sql.Identifier, columns))
                    vals_sql = sql.SQL(', ').join([sql.Placeholder()] * len(columns))

                    insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                        sql.Identifier(*TABLE_NAME.split('.')),
                        cols_sql,
                        vals_sql
                    )

                    # Преобразуем список словарей в список кортежей для executemany
                    data_to_insert = [tuple(file[col] for col in columns) for file in new_files]

                    cursor.executemany(insert_query, data_to_insert)
                    logging.info(f"Успешно добавлено {len(new_files)} новых записей.")

                # Обновляем файлы, требующие корректировки
                if files_to_update:
                    logging.info(f"Подготовка к обновлению {len(files_to_update)} записей...")
                    # Колонки для обновления - убедитесь, что они соответствуют вашей таблице
                    update_cols = [
                        'dt_modified', 'dt_create', 'size_kb',
                        'field_count', 'field_list', 'row_count',
                        'target_folder', 'file_name', # Обновим и эти поля на всякий случай
                        'dt_package', 'package_num'    # И информацию о пакете
                    ]
                    set_sql_parts = [sql.SQL("{} = %s").format(sql.Identifier(col)) for col in update_cols]
                    # Добавляем сброс флагов обработки и ошибок
                    set_sql_parts.append(sql.SQL("dt_processed = NULL"))
                    set_sql_parts.append(sql.SQL("is_error = FALSE"))
                    set_sql_parts.append(sql.SQL("error_message = NULL"))

                    update_query = sql.SQL("UPDATE {} SET {} WHERE full_path = %s").format(
                        sql.Identifier(*TABLE_NAME.split('.')),
                        sql.SQL(', ').join(set_sql_parts)
                    )

                    update_count = 0
                    for file in files_to_update:
                        # Формируем кортеж значений в правильном порядке + full_path для WHERE
                        values_to_update = tuple(file[col] for col in update_cols) + (file['full_path'],)
                        try:
                            cursor.execute(update_query, values_to_update)
                            update_count += 1
                            logging.debug(f"Запись для '{file['full_path']}' помечена к обновлению.")
                        except Exception as update_err:
                             logging.error(f"Ошибка при обновлении записи для {file['full_path']}: {update_err}")

                    logging.info(f"Успешно обновлено {update_count} записей (включая записи с NULL dt_modified).")

                # Коммитим изменения только если все прошло успешно
                conn.commit()
                logging.info("Изменения успешно сохранены в базе данных.")

    except psycopg2.OperationalError as e:
         logging.error(f"Ошибка подключения к базе данных: {e}")
         # Не выбрасываем исключение дальше, чтобы finally выполнился
    except Exception as e:
        logging.error(f"Ошибка при работе с базой данных: {str(e)}", exc_info=True)
        # Не выбрасываем исключение дальше, чтобы finally выполнился

def main():
    """Основная функция"""
    start_time = datetime.now()
    logging.info(f"=== Начало обработки ===")
    logging.info(f"Стартовая директория: {START_DIR}")
    logging.info(f"Таблица реестра: {TABLE_NAME}")

    try:
        # 1. Сканируем файлы и получаем данные только для валидных
        valid_files = scan_files(START_DIR)

        # 2. Обновляем базу данных на основе валидных файлов
        if valid_files: # Только если есть что обновлять
            update_database(valid_files)
        else:
             logging.info("Не найдено валидных файлов для обработки в базе данных.")

    except Exception as e:
        # Ловим любые другие неожиданные ошибки на верхнем уровне
        logging.critical(f"Критическая ошибка в процессе выполнения: {str(e)}", exc_info=True)
    finally:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logging.info(f"=== Обработка завершена за {duration:.2f} сек ===")

if __name__ == "__main__":
    main()