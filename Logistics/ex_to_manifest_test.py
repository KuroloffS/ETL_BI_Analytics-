import os
import logging
import pandas as pd
import psycopg2
from psycopg2 import pool, sql
from datetime import datetime
from openpyxl import load_workbook
from dotenv import load_dotenv
import json
import numpy as np

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
LOG_FILE = "process_to_manifest.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8",
)
logger = logging.getLogger()

# Реквизиты подключения к базе данных
DB_NAME = os.getenv("DB_NAME")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Начальная директория поиска
db_target_table = "manifest"
db_source_table = "excel_registry"
SCHEMA_EXCEL = "schema_excel.json"
SCHEMA_MANIFEST = "schema_manifest.json"
TIME_SESSION = datetime.now()

def load_schema(schema_path):
    """Загружает схему из JSON."""
    try:
        with open(schema_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        logger.error(f"Файл {schema_path} не найден.")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON файла {schema_path}: {e}")
        raise

def upsert_data(cursor, conn, data, table_name, schema):
    """Выполняет вставку или обновление данных в таблице."""
    try:
        unique_key = "itemid"
        columns = [col["db_name"] for col in schema]
        insert_query = sql.SQL("""
            INSERT INTO {table} ({columns})
            VALUES ({placeholders})
            ON CONFLICT ({unique_key}) DO UPDATE
            SET {updates};
        """).format(
            table=sql.Identifier(table_name),
            columns=sql.SQL(", ").join(map(sql.Identifier, columns)),
            placeholders=sql.SQL(", ").join(sql.Placeholder() for _ in columns),
            unique_key=sql.Identifier(unique_key),
            updates=sql.SQL(", ").join(
                sql.SQL(f"{col} = EXCLUDED.{col}") for col in columns if col != unique_key
            ),
        )

        for record in data:
            values = [record[col] for col in columns]
            cursor.execute(insert_query, values)

        conn.commit()
        logger.info(f"Данные успешно записаны в таблицу {table_name}.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка выполнения upsert операции: {e}")
        raise

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
        logger.info(f"Обновлен реестр для файла ID {record_id}: dt_processed={dt_processed}, is_error={is_error}.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка обновления реестра для файла ID {record_id}: {e}")
        raise

def process_excel_file(file_path, schema_excel):
    """Обрабатывает Excel-файл и возвращает DataFrame."""
    try:
        raw_df = pd.read_excel(file_path, sheet_name=0, engine="openpyxl")
        logger.debug(f"Файл {file_path} успешно прочитан. Колонки: {list(raw_df.columns)}")

        rename_map = {schema["originalName"]: schema["db_name"] for schema in schema_excel}
        selected_columns = [col["originalName"] for col in schema_excel if col["originalName"] in raw_df.columns]

        filtered_df = raw_df[selected_columns].copy()
        filtered_df.rename(columns=rename_map, inplace=True)

        required_columns = {schema["db_name"] for schema in schema_excel}
        missing_columns = required_columns - set(filtered_df.columns)

        for missing_col in missing_columns:
            datatype = next((schema["datatype"] for schema in schema_excel if schema["db_name"] == missing_col), None)
            filtered_df[missing_col] = "" if datatype == "str" else None

        for schema in schema_excel:
            db_name = schema["db_name"]
            datatype = schema["datatype"]
            if db_name in filtered_df.columns:
                filtered_df[db_name] = pd.to_numeric(filtered_df[db_name], errors="coerce") if datatype == "int64" else filtered_df[db_name].astype(datatype)

        logger.info(f"Файл {file_path} успешно обработан.")
        return filtered_df
    except Exception as e:
        logger.error(f"Ошибка обработки файла {file_path}: {e}")
        raise

def excel_to_db(missing_files, schema_excel, schema_manifest, conn, cursor):
    for record_id, full_path, dt_package, package_num in missing_files:
        logger.info(f"Начата обработка файла: {full_path}")
        try:
            filtered_df = process_excel_file(full_path, schema_excel)

            filtered_df = filtered_df.assign(
                dtflow=TIME_SESSION,
                dt_package=dt_package,
                package_num=package_num,
                source_file_name=full_path,
                id_registry=record_id,
            )

            for schema in schema_manifest:
                db_name = schema["db_name"]
                datatype = schema["datatype"]
                if datatype == "str" and db_name in filtered_df.columns:
                    filtered_df[db_name] = filtered_df[db_name].apply(lambda x: x if x is not None else "")

            data_to_upsert = filtered_df.replace({np.nan: None}).to_dict(orient="records")
            if not data_to_upsert:
                logger.warning(f"Файл {full_path} пустой или недействительный.")
                update_excel_registry(cursor, conn, record_id, is_error=True, error_message="Empty or invalid file")
                continue

            upsert_data(cursor, conn, data_to_upsert, db_target_table, schema_manifest)
            update_excel_registry(cursor, conn, record_id, dt_processed=datetime.now(), is_error=False)

        except Exception as e:
            logger.error(f"Ошибка при обработке файла {full_path}: {e}")
            update_excel_registry(cursor, conn, record_id, is_error=True, error_message=str(e))

def manifest_main():
    try:
        db_pool = psycopg2.pool.SimpleConnectionPool(
            1, 10,
            dbname=DB_NAME,
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
        )
        schema_manifest = load_schema(SCHEMA_MANIFEST)
        schema_excel = load_schema(SCHEMA_EXCEL)

        with db_pool.getconn() as conn:
            with conn.cursor() as cursor:
                excel_files = get_files_for_processing(cursor)

                if not excel_files:
                    logger.info("Нет Excel файлов для обработки.")
                    return

                excel_to_db(excel_files, schema_excel, schema_manifest, conn, cursor)

    except Exception as e:
        logger.error(f"Ошибка подключения к базе данных: {e}")
    finally:
        db_pool.closeall()
        logger.info("Завершение работы программы.")

if __name__ == "__main__":
    manifest_main()
