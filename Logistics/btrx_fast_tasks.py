import os
import json
from fast_bitrix24 import Bitrix
from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql
from datetime import datetime, timedelta

# Загрузка переменных окружения
load_dotenv()

# Реквизиты подключения к базе данных
DB_NAME = os.getenv('DB_NAME')
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

# Подключение к базе данных
def get_db_connection():
    return psycopg2.connect(
        dbname=DB_NAME,
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD
    )

# Схема соответствия полей
schema = {
    "subordinate": "subordinate",
    "id": "id",
    "parentId": "parent_id",
    "title": "title",
    "description": "description",
    "multitask": "multitask",
    "stageId": "stage_id",
    "createdBy": "created_by",
    "responsibleId": "responsibleid",
    "createdDate": "created_date",
    "changedDate": "changed_date",
    "closedDate": "closed_date",
    "dateStart": "date_start",
    "changedBy": "changed_by",
    "statusChangedBy": "status_changed_by",
    "closedBy": "closed_by",
    "durationFact": "duration_fact",
    "timeEstimate": "time_estimate",
    "timeSpentInLogs": "time_spent_in_logs",
    "descriptionInBbcode": "description_in_bbcode",
    "status": "status",
    "durationPlan": "duration_plan",
    "groupId": "groupid",
    "auditors": "auditors",
    "accomplices": "accomplices"
}

# Функция для получения времени отсчёта
def get_start_date():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT dtflow FROM btrx.tasks LIMIT 1;")
                result = cursor.fetchone()
                if result:
                    return result[0] - timedelta(days=1)
                else:
                    return datetime(1970, 1, 1)
    except Exception as e:
        raise Exception(f"Ошибка получения времени из базы данных: {e}")

# Функция для получения задач из Bitrix24
def get_tasks(start_date):
    params = {
        'filter': {
            '>=CHANGED_DATE': start_date.isoformat()
        },
        'select': [
            "SUBORDINATE", "ID", "PARENT_ID", "STATUS", "TITLE", "DESCRIPTION", "MULTITASK", "STAGE_ID",
            "GROUP_ID", "CREATED_BY", "RESPONSIBLE_ID", "ACCOMPLICES", "AUDITORS",
            "CREATED_DATE", "CHANGED_DATE", "CLOSED_DATE", "DATE_START",
            "CHANGED_BY", "STATUS_CHANGED_BY", "CLOSED_BY",
            "DURATION_PLAN", "DURATION_FACT", "TIME_ESTIMATE", "TIME_SPENT_IN_LOGS"
        ]
    }
    return bx.get_all('tasks.task.list', params=params)

# Преобразование вложенных полей в JSON
def convert_dicts_and_lists_to_json(task):
    for key, value in task.items():
        if isinstance(value, (dict, list)):
            task[key] = json.dumps(value)
    return task

# Функция для выполнения upsert в базу данных
def upsert_data(cursor, conn, data, table_name, schema):
    try:
        unique_key = 'id'
        columns = [schema[col] for col in schema]
        insert_query = sql.SQL("""
        INSERT INTO {} ({})
        VALUES ({})
        ON CONFLICT ({}) DO UPDATE
        SET {};
        """).format(
            sql.SQL(table_name),
            sql.SQL(', ').join(map(sql.Identifier, columns)),
            sql.SQL(', ').join(sql.Placeholder() for _ in columns),
            sql.Identifier(unique_key),
            sql.SQL(', ').join(
                sql.SQL(f"{col} = EXCLUDED.{col}") for col in columns if col != unique_key
            )
        )

        prepared_data = [[record.get(col, None) for col in schema] for record in data]
        cursor.executemany(insert_query, prepared_data)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise Exception(f"Ошибка выполнения upsert операции: {e}")

# Основной код
webhook = "https://antria.bitrix24.ru/rest/373/5onlworbqe6mtuta/"
bx = Bitrix(webhook)
table_name = 'btrx.tasks'

try:
    start_date = get_start_date()
    print(f'start_date: {start_date}')
    tasks = get_tasks(start_date)

    prepared_tasks = [convert_dicts_and_lists_to_json(task) for task in tasks]

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            upsert_data(cur, conn, prepared_tasks, table_name, schema)

    print("Данные успешно записаны в базу данных.")

except Exception as e:
    print(f"Произошла ошибка: {e}")
