import os
import re
import pandas as pd
from datetime import datetime
import time
from dotenv import load_dotenv
from sqlalchemy import create_engine

# Загрузить переменные из .env файла
load_dotenv()

# Получение переменных окружения
DB_NAME = os.getenv('DB_NAME')
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

# Путь к папке с файлами
MANIFEST_DIR = os.getenv('MANIFEST_DIR', r'\\10.1.19.245\C2M Logistics\2023')

# Текущая дата и время для поля dtflow
DTFLOW = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# Список необходимых полей в нижнем регистре
REQUIRED_COLUMNS = [
    'parceledirecvdate',
    'bigbagrecvdate',
    'consigneecountry',
    'value',
    'service',
    'dtflow',
    'dtcreate',
    'packageweight(g)'
]

# Функция для очистки имен колонок
def clean_column_names(columns):
    return [col.strip().replace('\n', '').lower() for col in columns]

# Функция для поиска и корректной обработки поля 'value'
def find_value_column(df_columns):
    for col in df_columns:
        if 'value' in col.lower():
            return col
    return None

# Функция для проверки наличия всех обязательных колонок
def check_required_columns(df_columns):
    missing_columns = [col for col in REQUIRED_COLUMNS if col not in df_columns]
    if missing_columns:
        print(f"Отсутствуют обязательные колонки: {', '.join(missing_columns)}")
        return False
    return True

# Функция для обработки одного Excel файла
def process_excel_file(file_path):
    dtcreate = datetime.fromtimestamp(os.path.getctime(file_path)).strftime('%Y-%m-%d %H:%M:%S')

    try:
        df = pd.read_excel(file_path, sheet_name=0, engine='openpyxl')

        if df.empty:
            print(f"Файл {file_path} пуст или не содержит данных.")
            return None

        df.columns = clean_column_names(df.columns)

        if 'productweight(g)' in df.columns:
            df.rename(columns={'productweight(g)': 'packageweight(g)'}, inplace=True)

        value_column = find_value_column(df.columns)
        if value_column:
            df.rename(columns={value_column: 'value'}, inplace=True)

        date_columns = ['parceledirecvdate', 'bigbagrecvdate']
        for col in date_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%d.%m.%Y %H:%M:%S')

        df = df.apply(lambda x: x.map(lambda y: ' '.join(str(y).splitlines())) if x.dtype == 'object' else x)

        df['dtflow'] = DTFLOW
        df['dtcreate'] = dtcreate

        # Проверка наличия всех обязательных колонок
        if not check_required_columns(df.columns):
            return None

        df_filtered = df[REQUIRED_COLUMNS]

        return df_filtered
    except Exception as e:
        print(f"Ошибка при обработке файла {file_path}: {e}")
        return None

# Подключение к базе данных
engine = create_engine(f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}')

# Переменные для статистики
processed_files = 0
total_rows = 0

start_time = time.time()

# Регулярное выражение для поиска всех вариантов написания "Manifest" и "Manyfest"
manifest_pattern = re.compile(r'manifest|manyfest', re.IGNORECASE)

def process_directory(directory):
    global processed_files, total_rows
    for root, dirs, files in os.walk(directory):
        # Проверка на наличие "Manifest" или "Manyfest" в пути
        if not manifest_pattern.search(root):
            continue
        for file in files:
            if file.endswith('.xlsx'):
                file_path = os.path.join(root, file)
                if os.path.getsize(file_path) > 500 * 1024:
                    df = process_excel_file(file_path)
                    if df is not None:
                        try:
                            df.to_sql('temp_manyfest', engine, if_exists='append', index=False)
                            print(f"Данные из файла {file_path} успешно загружены в базу данных.")
                            total_rows += len(df)
                        except Exception as e:
                            print(f"Ошибка при загрузке данных из файла {file_path} в базу: {e}")
                    processed_files += 1

process_directory(MANIFEST_DIR)

end_time = time.time()
execution_time = end_time - start_time

print(f"Время выполнения скрипта: {execution_time:.2f} секунд")
print(f"Количество обработанных файлов: {processed_files}")
print(f"Общее количество строк, загруженных в базу: {total_rows}")
