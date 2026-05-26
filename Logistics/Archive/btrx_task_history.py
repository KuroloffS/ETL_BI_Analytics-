import requests
import json

def get_task_history(webhook_url, task_id):
    """
    Получает историю задачи по её ID.

    :param webhook_url: URL вебхука для доступа к API Битрикс24
    :param task_id: ID задачи
    :return: История задачи в формате JSON
    """
    # Формируем URL для вызова метода
    url = f"{webhook_url}/tasks.task.history.list.json"
    
    # Параметры запроса
    params = {
        "taskId": task_id
    }
    
    # Отправляем запрос
    response = requests.post(url, json=params)
    
    # Проверяем статус ответа
    if response.status_code == 200:
        result = response.json()
        if "result" in result:
            return result["result"]  # Возвращаем историю задачи
        else:
            raise Exception(f"Ошибка в ответе API: {result}")
    else:
        raise Exception(f"Ошибка запроса: {response.status_code}, {response.text}")

# Пример использования
webhook_url = "https://antria.bitrix24.ru/rest/373/5onlworbqe6mtuta/"
task_id = 856

try:
    history = get_task_history(webhook_url, task_id)
    print(json.dumps(history, indent=4, ensure_ascii=False))  # Выводим историю задачи
except Exception as e:
    print(f"Произошла ошибка: {e}")