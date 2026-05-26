import json
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv
import os

# Загрузить переменные из .env файла
load_dotenv()

db_name = os.getenv('DB_NAME')
db_host = os.getenv('DB_HOST')
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')

# Функция для чтения JSON-файла и создания SQL-запроса
def create_table_from_json(json_file):
    with open(json_file, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    # Создание списка столбцов с типами данных
    columns = []
    for item in schema:
        column_name = item['db_name']
        data_type = item['datatype']
        columns.append(f"{column_name} {data_type}")

    # Формирование SQL-запроса для создания таблицы
    create_table_query = sql.SQL("""
    CREATE TABLE IF NOT EXISTS Manifest (
        id SERIAL PRIMARY KEY,
        {columns}
    );
    """).format(columns=sql.SQL(', ').join(map(sql.SQL, columns)))

    return create_table_query

# Функция для подключения к базе данных и выполнения SQL-запроса
def execute_sql_query(query):
    conn = psycopg2.connect(
        dbname=db_name,
        host=db_host,
        user=db_user,
        password=db_password
    )
    cursor = conn.cursor()
    cursor.execute(query)
    conn.commit()
    cursor.close()
    conn.close()

# Основная функция
def main():
    json_file = 'schema_manifest.json'
    create_table_query = create_table_from_json(json_file)
    execute_sql_query(create_table_query)
    print("Таблица Manifest успешно создана.")

if __name__ == "__main__":
    main()