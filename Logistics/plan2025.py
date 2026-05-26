import pandas as pd
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv
import os

# Загрузка переменных окружения
load_dotenv()

# Реквизиты подключения к базе данных
DB_NAME = os.getenv('DB_NAME')
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

# Путь к файлу Excel
test_file = r'\\10.1.19.245\C2M Logistics\BI Analytics\Plan\План 2025  for db.xlsx'

# Чтение данных из Excel
df = pd.read_excel(test_file, sheet_name=0, engine='openpyxl')
print(df)

# Замена запятых на точки в столбце Value и преобразование в числовой формат
df['value'] = df['value'].astype(str).str.replace(',', '.').astype(float)

# Подключение к базе данных PostgreSQL
try:
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST
    )
    cursor = conn.cursor()

    # Создание таблицы, если её нет
    create_table_query = """
    CREATE TABLE IF NOT EXISTS c2m_plan_2025 (
        country VARCHAR(50),
        service VARCHAR(50),
        item VARCHAR(50),
        tariff_range VARCHAR(50),
        value NUMERIC,
        period DATE,
        linehall VARCHAR(50),
        tariff NUMERIC,
        revenue NUMERIC
    );
    """
    cursor.execute(create_table_query)
    conn.commit()

    # Вставка данных в таблицу
    for _, row in df.iterrows():
        insert_query = sql.SQL("""
        INSERT INTO c2m_plan_2025 (country, service, item, tariff_range, value, period, linehall, tariff, revenue)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
        """)
        cursor.execute(insert_query, (
            row['country'], row['service'], row['item'], row['tariff_range'],
            row['value'], row['period'], row['linehall'], row['tariff'], row['revenue']
        ))
    conn.commit()

    print("Данные успешно записаны в таблицу c2m_plan_2025.")

except Exception as e:
    print(f"Ошибка: {e}")

finally:
    if conn:
        cursor.close()
        conn.close()