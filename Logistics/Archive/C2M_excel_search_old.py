import os
import re
import psycopg2
from psycopg2 import sql
from datetime import datetime
from openpyxl import load_workbook
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Реквизиты подключения к базе данных
DB_NAME = os.getenv('DB_NAME')
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

# Начальная директория поиска
#START_DIR = r"\\10.1.19.245\C2M Logistics\test"
START_DIR = r'\\10.1.19.245\C2M Logistics\2025\CAINIAO' 
#START_DIR = r'\\10.1.19.245\C2M Logistics\2024\CAINIAO'
TABLE_NAME = 'excel_registry'

# Шаблон для файлов
FILE_PATTERN = re.compile(r".*\.xlsx$")

# Регулярное выражение для разбора target_folder для поиска номера партии и даты
PACKAGE_PATTERN = re.compile(r"-\s*(\d+).*?\((\d{2}\.\d{2}\.\d{4})\)")

def check_required_columns(headers):
    # Список обязательных колонок (жесткое совпадение)
    required_columns = ["cartonid", "itemid", "masterno", "ordercode", "consigneecountry", "service", "danger_type"]         
    
    # Проверяем наличие обязательных колонок с жестким совпадением
    missing_columns = [col for col in required_columns if col not in headers]

    # Проверяем наличие хотя бы одной колонки с подстрокой "Weight(g)"
    weight_column_present = any("weight" in col for col in headers)  #Weight(g)

    # Если обязательные колонки или Weight(g)-колонка отсутствуют, поднимаем исключение
    if missing_columns or not weight_column_present:
        raise ValueError(
            f"Отсутствуют обязательные колонки: {', '.join(missing_columns)}. "
            f"Или отсутствует колонка с подстрокой 'weight'."
        )

    # Если все проверки пройдены, возвращаем заголовки
    return headers


def process_excel_file(file_path):
    """Проверяет Excel-файл на наличие нужных колонок."""
    try:
        workbook = load_workbook(filename=file_path, read_only=True)
        sheet = workbook.active  # Первый лист

        # Проверяем, есть ли строки в листе
        if sheet.max_row < 1:
            raise ValueError(f"Файл {file_path} не содержит данных")

        # Читаем заголовки и приводим их к нижнему регистру
        headers = [cell.value.lower() for cell in sheet[1] if cell.value]
        if not headers:
            raise ValueError(f"Первая строка в файле {file_path} пуста")

        try:
            # Проверяем наличие обязательных колонок
            checked_headers = check_required_columns(headers)
            print("Все обязательные колонки присутствуют:", checked_headers)
            return checked_headers
        except ValueError as e:
            print(f"[ERROR] Ошибка при обработке файла check_required_columns - {file_path}: {e}")
            return
        
    except Exception as e:
        print(f"Ошибка при обработке файла {file_path}: {e}")
        raise

def is_file_in_registry(cursor, file_path):
    """Проверяет, существует ли файл в реестре."""
    query = f"""
        SELECT EXISTS (
            SELECT 1
            FROM {TABLE_NAME}
            WHERE full_path = %s
        );
    """
    cursor.execute(query, (file_path,))
    return cursor.fetchone()[0]

def update_registry_entry(cursor, conn, file_path, is_error, error_message):
    """Обновляет запись в реестре."""
    update_query = f"""
        UPDATE {TABLE_NAME}
        SET is_error = %s, error_message = %s
        WHERE full_path = %s
    """
    cursor.execute(update_query, (is_error, error_message, file_path))
    conn.commit()

def find_files_and_save_to_registry(start_dir):
    data_to_insert = []
    try:
        # Подключение к базе данных
        conn = psycopg2.connect(
            dbname=DB_NAME,
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cursor = conn.cursor()

        for root, dirs, files in os.walk(start_dir):
            for file in files:
                if file.startswith('~$'):
                    continue  # Пропускаем временные файлы

                if FILE_PATTERN.match(file):
                    file_path = os.path.join(root, file)
                    file_stat = os.stat(file_path)
                    file_dt_create = datetime.fromtimestamp(file_stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S')
                    print(f'Найден файл {file_path}')

                    # Проверяем, есть ли файл в реестре
                    if not is_file_in_registry(cursor, file_path):
                        target_folder = os.path.basename(root)
                        file_name = os.path.basename(file_path)

                        try:
                            headers = process_excel_file(file_path)
                            if headers:
                                print(f"Читаю файл: {file_path}")
                                file_size_kb = file_stat.st_size // 1024  # Размер в Кб
                                dtflow = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                field_count = len(headers)
                                field_list = ";".join(headers)
                                is_new = True
                                is_error = False
                                error_message = None

                                # Инициализируем dt_package и package_num
                                dt_package = None
                                package_num = None

                                # Пытаемся извлечь информацию о партии из target_folder
                                match = PACKAGE_PATTERN.search(file_path)
                                if match:
                                    package_num = match.group(1)
                                    dt_package = datetime.strptime(match.group(2), '%d.%m.%Y').strftime('%Y-%m-%d')

                                # Добавляем данные для вставки
                                data_to_insert.append(
                                    (target_folder, file_name, file_path, file_dt_create, file_size_kb, dtflow, field_count, field_list, is_new, is_error, error_message, dt_package, package_num)
                                )
                        except Exception as e:
                            print(f"Ошибка при обработке файла {file_path}: {e}")
                            is_new = False
                            is_error = True
                            error_message = str(e)
                            dt_package = None
                            package_num = None

                            # Добавляем запись об ошибке
                            data_to_insert.append(
                                (target_folder, file_name, file_path, None, None, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 0, None, is_new, is_error, error_message, dt_package, package_num)
                            )

        # Если есть данные для вставки, сохраняем их
        if data_to_insert:
            save_to_db(cursor, conn, data_to_insert)
        else:
            print("Новые файлы не найдены.")

    except Exception as e:
        print(f"Ошибка при выполнении поиска и записи: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def save_to_db(cursor, conn, data):
    """Сохраняет данные в базу данных."""
    try:
        insert_query = f"""
            INSERT INTO {TABLE_NAME} (
                target_folder, file_name, full_path, dt_create, size_kb, dtflow, field_count, field_list, is_new, is_error, error_message, dt_package, package_num
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        cursor.executemany(insert_query, data)
        conn.commit()
        print(f"Успешно записано {len(data)} новых строк в {TABLE_NAME} ")
    except Exception as e:
        print(f"Ошибка при записи данных в базу: {e}")
        conn.rollback()

if __name__ == "__main__":
    """
    Модуль осуществляет поиск файлов эксель в целевой папке
    Перебирается все уровни вложенных папок и находит эксель файлы, которые содержат обязательные колонки 
    
    если найденный файл отсутствует в реестре, данные об этом файле записываются в реестр
    если при чтении файла возникла ошибка, сообщение общибка записывается в поле error_message
    реестр используется для указания на файл, данные из которого нужно записать в базу в таблицу manifest
    """
    find_files_and_save_to_registry(START_DIR)