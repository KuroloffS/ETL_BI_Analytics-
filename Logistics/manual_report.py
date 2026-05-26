import os
import pandas as pd
import psycopg2
from psycopg2 import pool, extras 
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Реквизиты подключения к базе данных
DB_NAME = os.getenv('DB_NAME')
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

# Путь к директории с Excel-файлами
excel_directory = r"\\10.1.19.245\C2M Logistics\BI Analytics\Checking dshbrd"

# Словарь для переименования колонок
columns_mapping = {
    "CartonID":         "cartonid",
    "ItemID":           "itemid",
    "OrderCode":        "ordercode",
    "ProductWeight(g)": "productweight_g",
    "ProductWeight(kg)":"productweight_kg",
    "Tariff per kg":    "tariff_per_kg",
    "Tariff per item":  "tariff_per_item",
    "Total for kg":     "total_for_kg",
    "Total":            "total",
    "ConsigneeCountry": "country",
    "Service":          "service",
    "liter":            "liter",
    "Service/Country":  "service_country",
    "Партия №":         "package_num",
    "Дата":             "package_date",
}

# Создание пула подключений к базе данных
pg_pool = psycopg2.pool.SimpleConnectionPool(
    1, 10,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST
)

# Функция для обработки файлов
def process_excel_files(directory):
    for file_name in os.listdir(directory):
        if file_name.endswith(".xlsx") or file_name.endswith(".xls"):
            file_path = os.path.join(directory, file_name)
            
            print(f'Processing file: {file_path}')
            
            try:
                # Чтение данных с листа "DATA 1"
                df = pd.read_excel(file_path, sheet_name="DATA 1", skiprows=1)
                print(f'File {file_name} read successfully')

                # Оставляем только нужные колонки
                df = df[[col for col in columns_mapping.keys() if col in df.columns]]

                # Переименовываем колонки
                df.rename(columns=columns_mapping, inplace=True)
                #print(df[df['productweight_g'].isna()])  # Вывод строк с нечисловыми значениями

                # Очистка данных в столбце productweight_g
                if 'productweight_g' in df.columns:
                    # Проверка на числовые значения
                    df['productweight_g'] = pd.to_numeric(df['productweight_g'], errors='coerce')
                    # Замена нечисловых значений на 0
                    df['productweight_g'] = df['productweight_g'].fillna(value=0)
                
                print(df.head())

                # Преобразуем DataFrame в список кортежей для пакетной вставки
                data_tuples = [tuple(x) for x in df.to_numpy()]
                columns = ','.join(df.columns)

                # Подготовка SQL-запроса для пакетной вставки
                insert_query = f"INSERT INTO manifest_manual ({columns}) VALUES %s"

                # Использование пула подключений
                conn = pg_pool.getconn()
                try:
                    with conn.cursor() as cur:
                        # Пакетная вставка данных
                        psycopg2.extras.execute_values(cur, insert_query, data_tuples)
                        conn.commit()
                        print(f'File {file_name} successfully written to DB')
                except Exception as e:
                    print(f"Error writing to DB from file {file_name}: {e}")
                finally:
                    pg_pool.putconn(conn)

            except Exception as e:
                print(f"Error reading file {file_name}: {e}")

# Запуск обработки файлов
process_excel_files(excel_directory)

# Закрытие пула подключений
pg_pool.closeall()