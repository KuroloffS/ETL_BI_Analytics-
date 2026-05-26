import psycopg2
from psycopg2 import pool
import json
import pandas as pd
from datetime import datetime
import os
from db_utils import upsert_data
from excel_processor import prepare_data


# Настройки подключения к базе данных
DB_NAME = os.getenv('DB_NAME')
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

SCHEMA_EXCEL = 'schema_c2m_excel.json'
SCHEMA_C2M = 'schema_c2m_logistics.json'
db_target_table = 'c2m_logistic'  # 'public.c2m_logistics'
db_source_table = 'excel_registry'  # 'public.excel_registry'


def load_schema(schema_path):
    """Загружает схему из JSON."""
    with open(schema_path, 'r', encoding='utf-8') as file:
        return json.load(file)


def get_pending_files(cursor):
    """Получает список файлов для обработки."""
    query = f"""
        SELECT id, full_path, dt_package, package_num 
        FROM {db_source_table} 
        WHERE dt_processed IS NULL AND id = 1942;
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


def excel_to_db():
    # Загружаем схемы
    schema_excel = load_schema(SCHEMA_EXCEL)
    schema_c2m = load_schema(SCHEMA_C2M)

    try:
        db_pool = psycopg2.pool.SimpleConnectionPool(
            1, 10,
            dbname=DB_NAME,
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD
        )

        # Получаем соединение из пула
        with db_pool.getconn() as conn:
            with conn.cursor() as cursor:
                pending_files = get_pending_files(cursor)

                # Убедимся, что pending_files итерируемый
                if not pending_files:
                    print("Нет файлов для обработки.")
                    return
                if not isinstance(pending_files, list):  # Преобразуем в список при необходимости
                    pending_files = list(pending_files)
                    
                print(type(pending_files))  # Ожидается: <class 'list'> или <class 'tuple'>
                
                print(f"[DEBUG] Pending files content: {pending_files}")
                for idx, record in enumerate(pending_files):
                    print(f"[DEBUG] Record #{idx}: {record} (type: {type(record)})")

                for record in pending_files:
                    # Проверка структуры
                    if not isinstance(record, (list, tuple)) or len(record) != 4:
                        print(f"[ERROR] Некорректная структура записи: {record}")
                        continue  # Пропускаем некорректные записи

                    # Распаковка
                    record_id, full_path, dt_package, package_num = record
                    print(f"[INFO] Processing file: {full_path}")

                    try:
                        # Подготовка данных
                        df = prepare_data(full_path, schema_excel)
                        if df is None or df.empty:
                            print(f"[WARNING] File {full_path} is empty or invalid.")
                            update_excel_registry(cursor, conn, record_id, is_error=True, error_message="Empty or invalid file")
                            continue  # Пропускаем текущую итерацию, но цикл продолжается

                        # Успешная обработка
                        print(f"[INFO] Successfully processed file: {full_path}")
                        df['dtflow'] = datetime.now()
                        df['dt_package'] = dt_package
                        df['package_num'] = package_num
                        df['source_file_name'] = full_path
                        df['id_registry'] = record_id

                        # Запись в базу данных
                        data_to_upsert = df.to_dict('records')
                        error_message = upsert_data(cursor, conn, data_to_upsert, db_target_table, schema_c2m)
                        if error_message:
                            update_excel_registry(cursor, conn, record_id, is_error=True, error_message=error_message)
                            continue

                        # Обновляем реестр
                        update_excel_registry(cursor, conn, record_id, dt_processed=datetime.now(), is_error=False)

                    except Exception as e:
                        print(f"[ERROR] Processing error for file {full_path}: {e}")
                        update_excel_registry(cursor, conn, record_id, is_error=True, error_message=str(e))

                # Если все файлы обработаны, выходим из функции
                print("[INFO] All files processed. Exiting function.")
                return

    except Exception as e:
        print(f"Ошибка подключения к базе данных: {e}")
    finally:
        # Закрытие всех соединений пула
        db_pool.closeall()


if __name__ == "__main__":
    excel_to_db()
