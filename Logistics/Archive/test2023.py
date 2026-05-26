import os
import pandas as pd
from datetime import datetime
import time
from dotenv import load_dotenv
from sqlalchemy import create_engine

# Загрузить переменные из .env файла
load_dotenv()

db_name = os.getenv('DB_NAME')
db_host = os.getenv('DB_HOST')
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')

# Путь к папке с файлами
#manifest_dir = r'\\10.1.19.245\C2M Logistics\2023'
manifest_dir = r'C:\Users\admin\Documents\2023test'

# Текущая дата и время для поля dtflow
dtflow = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# Список необходимых полей в нижнем регистре
required_columns = [
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
    cleaned_columns = []
    for col in columns:
        cleaned_col = col.strip().replace('\n', '').lower()
        cleaned_columns.append(cleaned_col)
    return cleaned_columns

# Функция для поиска и корректной обработки поля 'value'
def find_value_column(df_columns):
    for col in df_columns:
        if 'value' in col.lower():
            return col
    return None

# Функция для обработки одного Excel файла
def process_excel_file(file_path):
    global total_rows
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

        df['dtflow'] = dtflow
        df['dtcreate'] = dtcreate

        df_filtered = df[[col for col in required_columns if col in df.columns]]

        total_rows += len(df_filtered)
        return df_filtered
    except Exception as e:
        print(f"Ошибка при обработке файла {file_path}: {e}")
        return None

# Подключение к базе данных
engine = create_engine(f'postgresql://{db_user}:{db_password}@{db_host}/{db_name}')

# Переменные для статистики
processed_files = 0
total_rows = 0

start_time = time.time()

def process_directory(directory):
    global processed_files
    for root, dirs, files in os.walk(directory):
        if 'Manifest' not in root.split(os.sep):
            continue
        for file in files:
            if file.endswith('.xlsx'):
                file_path = os.path.join(root, file)
                if os.path.getsize(file_path) > 500 * 1024:
                    df = process_excel_file(file_path)
                    if df is not None:
                        try:
                            df.to_sql('temp_manifest', engine, if_exists='append', index=False)
                            print(f"Данные из файла {file_path} успешно загружены в базу данных.")
                        except Exception as e:
                            print(f"Ошибка при загрузке данных из файла {file_path} в базу: {e}")
                    processed_files += 1

process_directory(manifest_dir)

end_time = time.time()
execution_time = end_time - start_time

print(f"Время выполнения скрипта: {execution_time:.2f} секунд")
print(f"Количество обработанных файлов: {processed_files}")
print(f"Общее количество строк, загруженных в базу: {total_rows}")
