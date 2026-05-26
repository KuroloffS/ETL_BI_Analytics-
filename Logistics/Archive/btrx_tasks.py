import requests
import json
import pandas as pd

def get_tasks(webhook_url, start_date=None, end_date=None):
    """
    Получает список задач из Битрикс24 по дате создания.

    :param webhook_url: URL вебхука для доступа к API Битрикс24
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

    tasks_data = []
    url = f"{webhook_url}/tasks.task.list.json"

    while True:
        response = requests.post(url, json=params)
        if response.status_code != 200:
            raise Exception(f"Ошибка запроса: {response.status_code}, {response.text}")

        result = response.json()
        if 'result' in result and 'tasks' in result['result']:
            tasks = result['result']['tasks']
            tasks_data.extend(tasks)

            # Проверяем, есть ли еще данные для загрузки
            if 'next' in result['result'] and result['result']['next'] is not None:
                params['start'] = result['result']['next']
            else:
                break
        else:
            break

    return tasks_data

# Пример использования
webhook_url = "https://antria.bitrix24.ru/rest/373/5onlworbqe6mtuta/"
start_date = "2024-12-01"
end_date = "2024-12-31"

try:
    tasks = get_tasks(webhook_url, start_date, end_date)

    # Записываем данные в файл JSON
    with open('tasks.json', 'w', encoding='utf-8') as json_file:
        json.dump(tasks, json_file, indent=4, ensure_ascii=False)

    df = pd.DataFrame(tasks)
    print(df.head())
    #print(json.dumps(tasks, indent=4, ensure_ascii=False))
except Exception as e:
    print(f"Произошла ошибка: {e}")