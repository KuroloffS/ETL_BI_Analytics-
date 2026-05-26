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
db_target_table = 'public.c2m_temp'  # 'public.c2m_logistics'
db_source_table = 'public.excel_registry'  # 'public.excel_registry'


def load_schema(schema_path):
    """Загружает схему из JSON."""
    with open(schema_path, 'r', encoding='utf-8') as file:
        return json.load(file)


def get_pending_files(cursor):
    """Получает список файлов для обработки."""
    query = f"""
        SELECT id, full_path, dt_package, package_num 
        FROM {db_source_table} 
        WHERE dt_processed IS NULL LIMIT 1;
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


def main():
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

                if not pending_files:
                    print("Нет файлов для обработки.")
                    return

                for record_id, full_path, dt_package, package_num in pending_files:
                    print(f"Обработка файла: {full_path}")

                    try:
                        dtmod = datetime.fromtimestamp(os.stat(full_path).st_ctime)
                        dtflow = datetime.now()

                        df = prepare_data(full_path, schema_excel)

                        if df is not None and not df.empty:
                            # Добавляем служебные данные
                            df['dtflow'] = dtflow
                            df['dt_package'] = dt_package
                            df['package_num'] = package_num
                            df['source_file_name'] = full_path

                            # Запись в базу
                            error_message = upsert_data(cursor, conn, df, db_target_table, schema_c2m)

                            if error_message:
                                update_excel_registry(cursor, conn, record_id, is_error=True, error_message=error_message)
                                print(error_message)
                                continue

                            # Обновление реестра после успешной обработки
                            update_excel_registry(cursor, conn, record_id, dt_processed=datetime.now(), is_error=False)
                        else:
                            print(f"Файл {full_path} не содержит данных для обработки.")
                            update_excel_registry(cursor, conn, record_id, is_error=True, error_message="Пустой файл")

                    except Exception as e:
                        error_message = f"Ошибка обработки файла {full_path}: {e}"
                        update_excel_registry(cursor, conn, record_id, is_error=True, error_message=error_message)
                        print(error_message)

    except Exception as e:
        print(f"Ошибка подключения к базе данных: {e}")
    finally:
        # Закрытие всех соединений пула
        db_pool.closeall()


if __name__ == "__main__":
    main()
