import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error
import xgboost as xgb
from datetime import datetime, timedelta

from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql
import json
import os

# Загрузить переменные из .env файла
load_dotenv()

db_name = os.getenv('DB_NAME')
db_host = os.getenv('DB_HOST')
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')

# Функция для чтения исторических данных из базы для обучения
def read_historical_data(db_name, db_host, db_user, db_password):
    try:
        # Подключение к базе данных PostgreSQL
        conn = psycopg2.connect(
            dbname=db_name,
            host=db_host,
            user=db_user,
            password=db_password
        )
        cursor = conn.cursor()

        query = r"""
        WITH res AS (SELECT
    date_trunc('month', bigbagrecvdate::timestamp without time zone) AS month,
    consigneecountry AS country,
    service,
    count(itemid) AS qty,
    sum(packageweight_g) AS weight
FROM public.manifest WHERE bigbagrecvdate IS NOT null
GROUP BY 1, 2, 3

UNION ALL

SELECT
    date_trunc('month', CASE
        WHEN bigbagrecvdate ~ '^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2}$'
        THEN to_timestamp(bigbagrecvdate, 'DD.MM.YYYY HH24:MI:SS')
    ELSE NULL
    END) AS month,
    consigneecountry AS country,
    service,
    count(*) AS qty,
    sum("packageweight(g)") AS weight
FROM public.temp_manyfest WHERE bigbagrecvdate IS NOT null
GROUP BY 1, 2, 3) SELECT * FROM res WHERE month IS NOT null

        """
        cursor.execute(query)
        data = cursor.fetchall()

        # Получение имен столбцов
        columns = [desc[0] for desc in cursor.description]

        # Создание DataFrame
        df = pd.DataFrame(data, columns=columns)

        return df

    except Exception as e:
        print(f"Ошибка при чтении данных из базы данных: {e}")
        return None

    finally:
        # Закрытие соединения с базой данных
        if conn:
            cursor.close()
            conn.close()    
    

# === Подготовка данных ===
def prepare_data(df):
    # Агрегация данных по месяцам, странам и сервисам
    #df['month'] = df['date'].dt.to_period('M')
    #monthly_data = df.groupby(['month', 'service', 'country']).sum().reset_index()
    
    monthly_data['month'] = df['month'].astype(str)

    # Преобразование категориальных признаков в числовые
    monthly_data = pd.get_dummies(monthly_data, columns=['service', 'country'], drop_first=True)

    return monthly_data
# === Обучение модели ===
def train_model(data):
    # Разделение данных на обучающую и тестовую выборки
    X = data.drop(columns=['weight', 'qty', 'month'])
    y = data[['weight', 'qty']]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # Обучение модели XGBoost для каждого целевого признака
    models = {}
    for target in ['weight', 'qty']:
        model = xgb.XGBRegressor(objective='reg:squarederror', random_state=42, n_estimators=100)
        model.fit(X_train, y_train[target])
        models[target] = model

        # Оценка качества модели
        y_pred = model.predict(X_test)
        rmse = mean_squared_error(y_test[target], y_pred, squared=False)
        print(f'RMSE for {target}: {rmse}')

    return models
# === Прогнозирование на следующий год ===
def predict_next_year(models, data):
    last_month = pd.to_datetime(data['month'].max() + '-01')
    future_dates = [(last_month + timedelta(days=i*30)).strftime('%Y-%m') for i in range(1, 13)]

    # Генерация базовых данных для прогноза
    services = data['service'].unique()
    countries = data['country'].unique()
    future_data = []
    for month in future_dates:
        for service in services:
            for country in countries:
                future_data.append([month, service, country])

    future_df = pd.DataFrame(future_data, columns=['month', 'service', 'country'])
    future_df = pd.get_dummies(future_df, columns=['service', 'country'], drop_first=True)

    # Приведение данных к нужному формату
    X_future = future_df.reindex(columns=data.drop(columns=['weight', 'qty']).columns, fill_value=0)

    # Прогнозирование
    predictions = {}
    for target, model in models.items():
        predictions[target] = model.predict(X_future)

    # Создание результирующей таблицы
    future_df['weight'] = predictions['weight']
    future_df['qty'] = predictions['qty']
    return future_df

# === Основной сценарий ===
if __name__ == '__main__':
    # получение исторических данных
    df = read_historical_data(db_name, db_host, db_user, db_password)

    # Подготовка данных
    data = prepare_data(df)

    # Обучение модели
    models = train_model(data)

    # Прогнозирование на следующий год
    predictions = predict_next_year(models, data)

    print(predictions.head())