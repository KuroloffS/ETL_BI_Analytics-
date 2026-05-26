import os
import pandas as pd
from datetime import datetime
import time
from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql
import re

# Загрузить переменные из .env файла
load_dotenv()

db_name = os.getenv('DB_NAME')
db_host = os.getenv('DB_HOST')
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')

# Путь к папке с файлами
manifest_dir = '\\10.1.19.245\C2M Logistics\2023'

# Функция для поиска последнего файла, начинающегося с "CAINIAO for DM"
def find_latest_file(directory):
    files = [f for f in os.listdir(directory) if f.lower().startswith('cainiao for dm') and f.lower().endswith('.xlsx')]
    if not files:
        raise FileNotFoundError("Файлы, начинающиеся с 'CAINIAO for DM', не найдены.")
    latest_file = max(files, key=lambda x: os.path.getctime(os.path.join(directory, x)))
    return os.path.join(directory, latest_file)

# Функция для обработки Excel файла
def process_excel_file(file_path):
    # Чтение листа "Logistics operations" и пропуск первой строки
    df = pd.read_excel(file_path, sheet_name='Logistics operations', skiprows=1, engine='openpyxl')

    # Преобразование всех данных в строки
    df = df.astype(str)

    return df

# Функция для очистки имен столбцов
def clean_column_names(columns):
    cleaned_columns = [re.sub(r'\W+', '_', col) for col in columns]
    return cleaned_columns

# Функция для создания таблицы в базе данных
def create_table(cursor, table_name, columns):
    cleaned_columns = clean_column_names(columns)
    columns_with_types = ', '.join([f"{col} TEXT" for col in cleaned_columns])
    create_table_query = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id SERIAL PRIMARY KEY,
        {columns_with_types}
    );
    """
    cursor.execute(create_table_query)

# Функция для вставки данных в таблицу
def insert_data(cursor, table_name, df):
    cleaned_columns = clean_column_names(df.columns)
    insert_query = sql.SQL("""
    INSERT INTO {table_name} ({columns}) VALUES ({placeholders});
    """).format(
        table_name=sql.Identifier(table_name),
        columns=sql.SQL(', ').join(map(sql.Identifier, cleaned_columns)),
        placeholders=sql.SQL(', ').join(sql.Placeholder() * len(cleaned_columns))
    )

    for row in df.itertuples(index=False, name=None):
        cursor.execute(insert_query, row)

# Основной код
try:
    # Поиск последнего файла
    latest_file_path = find_latest_file(manifest_dir)
    print(f"Найден последний файл: {latest_file_path}")

    # Обработка файла
    df = process_excel_file(latest_file_path)

    # Подключение к базе данных PostgreSQL
    conn = psycopg2.connect(
        dbname=db_name,
        host=db_host,
        user=db_user,
        password=db_password
    )
    cursor = conn.cursor()

    # Имя таблицы для записи
    table_name = 'temp_manifest'

    # Создание таблицы
    create_table(cursor, table_name, df.columns)

    # Вставка данных
    insert_data(cursor, table_name, df)

    conn.commit()
    cursor.close()
    conn.close()

    print("Данные успешно записаны в таблицу temp_manifest базы данных PostgreSQL")
except Exception as e:
    print(f"Ошибка: {e}")
