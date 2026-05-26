import os
import pandas as pd
import json
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

# Загрузить переменные из .env файла
load_dotenv()

db_name = os.getenv('DB_NAME')
db_host = os.getenv('DB_HOST')
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')

# Путь к папке с файлами
manifest_dir = '//10.1.19.245/C2M Logistics/CAINIAO for DM'
rename_fields_dic = 'schema_Cainiao_for_DM.json'

# Функция для поиска последнего файла, начинающегося с "Cainiao for DM"
def find_latest_file(directory):
    files = [f for f in os.listdir(directory) if f.lower().startswith('cainiao for dm') and f.lower().endswith('.xlsx')]
    if not files:
        raise FileNotFoundError("Файлы, начинающиеся с 'Cainiao for DM', не найдены.")
    latest_file = max(files, key=lambda x: os.path.getctime(os.path.join(directory, x)))
    return os.path.join(directory, latest_file)

# Функция для обработки Excel файла
def process_excel_file(file_path):
    # Чтение листа "Logistics operations" и пропуск первой строки
    df = pd.read_excel(file_path, sheet_name='Logistics operations', skiprows=1, engine='openpyxl')
    
    # Преобразование всех данных в строки
    df = df.astype(str)
    return df

# Функция для переименования столбцов на основе схемы
def rename_columns(df, schema_path):
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    # Создание словаря для переименования столбцов
    rename_mapping = {item['originalName']: item['db_name'] for item in schema}
    
    # Переименовываем столбцы в DataFrame
    df.rename(columns=rename_mapping, inplace=True)
    return df

# Функция для создания таблицы в базе данных
def create_table(cursor, table_name, columns):
    # Используем psycopg2.sql для безопасного составления запросов
    columns_with_types = ', '.join([f"{col} TEXT" for col in columns])
    create_table_query = sql.SQL("""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id SERIAL PRIMARY KEY,
        {columns_with_types}
    );
    """).format(
        table_name=sql.Identifier(table_name),
        columns_with_types=sql.SQL(columns_with_types)
    )
    
    cursor.execute(create_table_query)
    # Явный коммит, чтобы изменения были зафиксированы в базе
    cursor.connection.commit()

# Функция для удаления всех данных из таблицы
def clear_table(cursor, table_name):
    delete_query = sql.SQL("DELETE FROM {table_name}").format(
        table_name=sql.Identifier(table_name)
    )
    cursor.execute(delete_query)
    cursor.connection.commit()

# Функция для вставки данных в таблицу
def insert_data(cursor, table_name, df):
    cleaned_columns = df.columns
    insert_query = sql.SQL("""
    INSERT INTO {table_name} ({columns}) VALUES ({placeholders});
    """).format(
        table_name=sql.Identifier(table_name),
        columns=sql.SQL(', ').join(map(sql.Identifier, cleaned_columns)),
        placeholders=sql.SQL(', ').join(sql.Placeholder() * len(cleaned_columns))
    )

    # Вставка данных построчно
    for row in df.itertuples(index=False, name=None):
        cursor.execute(insert_query, row)

# Основной код
def main():
    try:
        # Поиск последнего файла
        latest_file_path = find_latest_file(manifest_dir)
        print(f"Найден последний файл: {latest_file_path}")

        # Обработка файла
        df = process_excel_file(latest_file_path)

        # Переименование столбцов на основе схемы
        df = rename_columns(df, rename_fields_dic)

        # Подключение к базе данных PostgreSQL
        with psycopg2.connect(
            dbname=db_name,
            host=db_host,
            user=db_user,
            password=db_password
        ) as conn:
            with conn.cursor() as cursor:
                # Имя таблицы
                table_name = 'cainiao_for_dm'
                
                # Создание таблицы, если она не существует
                create_table(cursor, table_name, df.columns)
                
                # Удаляем старые данные из таблицы
                clear_table(cursor, table_name)

                # Вставка новых данных
                insert_data(cursor, table_name, df)

        print("Данные успешно перезаписаны в базу данных PostgreSQL")
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    main()
