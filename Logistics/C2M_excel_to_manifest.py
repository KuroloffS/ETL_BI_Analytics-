import os
import pandas as pd
import psycopg2
from psycopg2 import pool, sql
from datetime import datetime
from openpyxl import load_workbook
from dotenv import load_dotenv
import json
import numpy as np
from db_utils import upsert_data

# Загрузка переменных окружения
load_dotenv()

# Реквизиты подключения к базе данных
DB_NAME = os.getenv('DB_NAME')
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

# Начальная директория поиска
#START_DIR = r'\\10.1.19.245\C2M Logistics\2024\CAINIAO'
db_target_table = 'manifest'    #manifest'
db_source_table = 'excel_registry'
SCHEMA_EXCEL ='schema_excel.json'
SCHEMA_MANIFEST = 'schema_manifest.json'
TIME_SESSION = datetime.now()

def load_schema(schema_path):
    """Загружает схему из JSON."""
    try:
        with open(schema_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        raise FileNotFoundError(f"Файл {schema_path} не найден.")
    except json.JSONDecodeError as e:
        raise ValueError(f"Ошибка парсинга JSON файла {schema_path}: {e}")

def upsert_data(cursor, conn, data, table_name, schema):

    # Подготовка запроса INSERT с ON CONFLICT
    try:
        unique_key = 'itemid'
        columns = [col['db_name'] for col in schema]
        insert_query = sql.SQL("""
        INSERT INTO {table} ({columns})
        VALUES ({placeholders})
        ON CONFLICT ({unique_key}) DO UPDATE
        SET {updates};
        """).format(
            table=sql.Identifier(table_name),
            columns=sql.SQL(', ').join(map(sql.Identifier, columns)),
            placeholders=sql.SQL(', ').join(sql.Placeholder() for _ in columns),
            unique_key=sql.Identifier(unique_key),
            updates=sql.SQL(', ').join(
                sql.SQL(f"{col} = EXCLUDED.{col}") for col in columns if col != unique_key
            )
        )

        # Выполнение вставки для каждой записи
        for record in data:
            values = [record[col] for col in columns]
            cursor.execute(insert_query, values)

        conn.commit()

        print(f"Данные успешно обработаны и записаны в таблицу {table_name}. \n\n")
    except Exception as e:
        conn.rollback()
        raise Exception(f"Ошибка выполнения upsert операции: {e}")

def get_files_for_processing(cursor):
    """Получает список файлов для обработки."""
    query = f"""
        SELECT id, full_path, dt_package, package_num 
        FROM {db_source_table} 
        WHERE dt_processed IS NULL AND dt_package IS NOT NULL;
    """
    cursor.execute(query)
    return cursor.fetchall()

def update_excel_registry(cursor, conn, record_id, dt_processed=None, is_error=False, error_message=None):
    """Обновляет excel_registry."""
    query = f"""
        UPDATE {db_source_table}
        SET 
            dt_processed = %s,
            is_error = %s,
            error_message = %s
        WHERE id = %s;
    """
    try:
        cursor.execute(query, (dt_processed, is_error, error_message, record_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise Exception(f"Ошибка обновления реестра: {e}")
    
def process_excel_file(file_path, schema_excel):
    """Обрабатывает Excel-файл и возвращает DataFrame."""
    try:
        raw_df = pd.read_excel(file_path, sheet_name=0, engine='openpyxl')
        print(f"[DEBUG] Columns in the file: {list(raw_df.columns)}")

        # Создаем карту переименования колонок
        rename_map = {schema["originalName"]: schema["db_name"] for schema in schema_excel}
        selected_columns = [col["originalName"] for col in schema_excel if col["originalName"] in raw_df.columns]

        filtered_df = raw_df[selected_columns].copy()  # Фильтруем нужные колонки
        filtered_df.rename(columns=rename_map, inplace=True)  # Переименовываем

        # Проверяем, есть ли обязательные колонки в DataFrame
        required_columns = {schema["db_name"] for schema in schema_excel}
        missing_columns = required_columns - set(filtered_df.columns)

        # Добавляем отсутствующие колонки со значением None
        #for missing_col in missing_columns:
        #    filtered_df[missing_col] = ''
        
        # Добавляем отсутствующие колонки
        for missing_col in missing_columns:
            # Проверяем тип данных для отсутствующих колонок
            datatype = next((schema["datatype"] for schema in schema_excel if schema["db_name"] == missing_col), None)
            filtered_df[missing_col] = '' if datatype == 'str' else None


        # Преобразуем типы данных
        for schema in schema_excel:
            db_name = schema["db_name"]
            datatype = schema["datatype"]
            if db_name in filtered_df.columns:
                filtered_df[db_name] = pd.to_numeric(filtered_df[db_name], errors='coerce') if datatype == 'int64' else filtered_df[db_name].astype(datatype)

        return filtered_df
    except Exception as e:
        raise ValueError(f"Ошибка обработки файла {file_path}: {e}")

def excel_to_db(missing_files, schema_excel, schema_manifest, conn, cursor):
    for record_id, full_path, dt_package, package_num in missing_files:
        print(f"[INFO] Processing file: {full_path}")
        try:
            filtered_df = process_excel_file(full_path, schema_excel)

            # Добавляем дополнительные поля
            filtered_df = filtered_df.assign(
                dtflow=TIME_SESSION,
                dt_package=dt_package,
                package_num=package_num,
                source_file_name=full_path,
                id_registry=record_id
            )

            # Преобразуем None в пустую строку для текстовых полей
            for schema in schema_manifest:
                db_name = schema["db_name"]
                datatype = schema["datatype"]
                if datatype == 'str' and db_name in filtered_df.columns:
                    filtered_df[db_name] = filtered_df[db_name].apply(lambda x: x if x is not None else '')  # Заменяем None на ''

            print(filtered_df.head())
            # Проверяем пустые значения
            data_to_upsert = filtered_df.replace({np.nan: None}).to_dict(orient='records')
            if not data_to_upsert:
                print(f"[WARNING] File {full_path} is empty or invalid.")
                update_excel_registry(cursor, conn, record_id, is_error=True, error_message="Empty or invalid file")
                continue
            
            # Записываем данные в БД
            upsert_data(cursor, conn, data_to_upsert, db_target_table, schema_manifest)

            # Обновляем реестр
            update_excel_registry(cursor, conn, record_id, dt_processed=datetime.now(), is_error=False)

        except Exception as e:
            print(f"[ERROR] Ошибка при обработке файла {full_path}: {e}")
            update_excel_registry(cursor, conn, record_id, is_error=True, error_message=str(e))


def manifest_main():
    try:
        db_pool = psycopg2.pool.SimpleConnectionPool(
            1, 10,
            dbname=DB_NAME,
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD
        )
        schema_manifest = load_schema(SCHEMA_MANIFEST)
        schema_excel = load_schema(SCHEMA_EXCEL)

        with db_pool.getconn() as conn:
            with conn.cursor() as cursor:
                excel_files = get_files_for_processing(cursor)

                if not excel_files:
                    print("Нет excel файлов для обработки.")
                    return

                excel_to_db(excel_files, schema_excel, schema_manifest, conn, cursor)

    except Exception as e:
        print(f"Ошибка подключения к базе данных: {e}")
    finally:
        db_pool.closeall()

if __name__ == "__main__":
    manifest_main()
