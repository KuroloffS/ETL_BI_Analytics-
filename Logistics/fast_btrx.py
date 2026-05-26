import os
import json
from fast_bitrix24 import Bitrix
from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql
from datetime import datetime

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

# Функция для получения задач из Bitrix24
def get_tasks(start_date=None, end_date=None):
    """
    Получает список задач из Битрикс24 по дате создания.

    :param start_date: Начальная дата для фильтрации задач (в формате YYYY-MM-DD)
    :param end_date: Конечная дата для фильтрации задач (в формате YYYY-MM-DD)
    :return: Список задач
    """
    params = {
        'filter': {
            '>=CHANGED_DATE': start_date,
            '<=CHANGED_DATE': end_date
        },
        'select': [
            "SUBORDINATE", "ID", "PARENT_ID", "STATUS", "TITLE", "DESCRIPTION", "MULTITASK", "STAGE_ID",
            "GROUP_ID", "CREATED_BY", "RESPONSIBLE_ID", "ACCOMPLICES", "AUDITORS",
            "CREATED_DATE", "CHANGED_DATE", "CLOSED_DATE", "DATE_START",
            "CHANGED_BY", "STATUS_CHANGED_BY", "CLOSED_BY",
            "DURATION_PLAN", "DURATION_FACT", "TIME_ESTIMATE", "TIME_SPENT_IN_LOGS"
        ]
    }

    # Используем метод get_all() для получения всех задач
    tasks_data = bx.get_all('tasks.task.list', params=params)
    return tasks_data

# Функция для раскрытия вложенных полей
def flatten_task(task):
    """
    Раскрывает вложенные поля в задаче.

    :param task: Словарь с данными задачи
    :return: Словарь с раскрытыми полями
    """
    flattened_task = task.copy()
    if 'group' in task:
        for key, value in task['group'].items():
            flattened_task[f"group.{key}"] = value
        del flattened_task['group']
    if 'creator' in task:
        for key, value in task['creator'].items():
            flattened_task[f"creator.{key}"] = value
        del flattened_task['creator']
    if 'responsible' in task:
        for key, value in task['responsible'].items():
            flattened_task[f"responsible.{key}"] = value
        del flattened_task['responsible']
    return flattened_task

# Функция для преобразования словарей и списков в строки JSON
def convert_dicts_and_lists_to_json(task):
    """
    Преобразует словари и списки в строки JSON.

    :param task: Словарь с данными задачи
    :return: Словарь с преобразованными данными
    """
    for key, value in task.items():
        if isinstance(value, dict) or isinstance(value, list):
            task[key] = json.dumps(value)
    return task

# Функция для приведения ключей к нижнему регистру и замены camelCase на snake_case
def normalize_keys(task):
    """
    Приводит все ключи в словаре к нижнему регистру и заменяет camelCase на snake_case.

    :param task: Словарь с данными задачи
    :return: Словарь с нормализованными ключами
    """
    normalized_task = {}
    for key, value in task.items():
        # Заменяем camelCase на snake_case
        normalized_key = key.lower().replace('.', '_').replace('id', '_id').replace('date', '_date').replace('inbbcode', 'in_bbcode').replace('changedby', 'changed_by').replace('statuschangedby', 'status_changed_by').replace('closedby', 'closed_by').replace('timeestimate', 'time_estimate').replace('timespentinlogs', 'time_spent_in_logs').replace('durationfact', 'duration_fact').replace('durationplan', 'duration_plan').replace('groupmemberscount', 'group_members_count').replace('groupadditionaldata', 'group_additional_data').replace('creatorworkposition', 'creator_work_position').replace('responsibleworkposition', 'responsible_work_position').replace('accomplicesdata', 'accomplices_data').replace('auditorsdata', 'auditors_data').replace('substatus', 'sub_status')
        normalized_task[normalized_key] = value
    return normalized_task

# Функция для выполнения upsert в базу данных
def upsert_tasks(tasks):
    """
    Выполняет upsert задач в таблицу btrx.tasks.

    :param tasks: Список задач
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for task in tasks:
                flattened_task = flatten_task(task)
                flattened_task = convert_dicts_and_lists_to_json(flattened_task)
                flattened_task = normalize_keys(flattened_task)  # Приводим ключи к нижнему регистру и заменяем camelCase на snake_case
                columns = flattened_task.keys()
                values = [flattened_task[column] for column in columns]

                # Формируем SQL-запрос для upsert
                query = sql.SQL("""
                    INSERT INTO btrx.tasks ({})
                    VALUES ({})
                    ON CONFLICT (id) DO UPDATE SET {}
                """).format(
                    sql.SQL(', ').join(map(sql.Identifier, columns)),
                    sql.SQL(', ').join(sql.Placeholder() * len(columns)),
                    sql.SQL(', ').join(
                        sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(col), sql.Identifier(col)) for col in columns
                    )
                )

                # Выполняем запрос
                cur.execute(query, values)
        conn.commit()

# Пример использования
webhook = "https://antria.bitrix24.ru/rest/373/5onlworbqe6mtuta/"
bx = Bitrix(webhook)

start_date = "2024-12-01"
end_date = "2024-12-31"

try:
    tasks = get_tasks(start_date, end_date)

    # Записываем данные в файл JSON
    with open('tasks.json', 'w', encoding='utf-8') as json_file:
        json.dump(tasks, json_file, indent=4, ensure_ascii=False)

    # Выполняем upsert в базу данных
    upsert_tasks(tasks)

    print("Данные успешно записаны в базу данных.")

except Exception as e:
    print(f"Произошла ошибка: {e}")