import os
import pandas as pd
from datetime import datetime
import time
from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql
import json

# Загрузить переменные из .env файла
load_dotenv()

db_name = os.getenv('DB_NAME')
db_host = os.getenv('DB_HOST')
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')

# Путь к папке с файлами
manifest_dir = '//10.1.19.245/C2M Logistics/2024'

# Текущая дата и время для поля dtflow
dtflow = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# Время начала выполнения скрипта
start_time = time.time()

# Загрузка схемы соответствия из JSON-файла
with open('schema_manifest.json', 'r', encoding='utf-8') as f:
    schema_manifest = json.load(f)

# Функция для записи данных в базу данных
def write_to_db(df, dtcreate, file_name):
    try:
        # Подключение к базе данных PostgreSQL
        conn = psycopg2.connect(
            dbname=db_name,
            host=db_host,
            user=db_user,
            password=db_password
        )
        cursor = conn.cursor()

        # Создание таблицы, если она не существует
        create_table_query = """
        CREATE TABLE IF NOT EXISTS manifest (
            id SERIAL PRIMARY KEY,
            {columns},
            UNIQUE (itemid) -- Добавление уникального ограничения на поле itemid
        );
        """
        columns = ', '.join([f"{item['db_name']} {item['datatype']}" for item in schema_manifest])
        cursor.execute(sql.SQL(create_table_query).format(columns=sql.SQL(columns)))
        conn.commit()

        # Подготовка запроса на вставку с обработкой конфликтов
        insert_query = sql.SQL("""
        INSERT INTO manifest ({columns})
        VALUES ({placeholders})
        ON CONFLICT (itemid) DO NOTHING;
        """).format(
            columns=sql.SQL(', ').join(map(sql.Identifier, [item['db_name'] for item in schema_manifest])),
            placeholders=sql.SQL(', ').join(sql.Placeholder() * len(schema_manifest))
        )

        # Вставка каждой строки в базу данных
        for row in df.itertuples(index=False, name=None):
            try:
                cursor.execute(insert_query, row)
            except Exception as e:
                print(f"Ошибка вставки строки: {e}")

        conn.commit()
        cursor.close()
        conn.close()
        print(f"Данные из файла {file_name} успешно обработаны.")
    except Exception as e:
        print(f"Ошибка записи в базу данных: {e}")


# Функция для обработки одного Excel файла
def process_excel_file(file_path):
    # Дата создания файла
    dtcreate = datetime.fromtimestamp(os.path.getctime(file_path)).strftime('%Y-%m-%d %H:%M:%S')

    # Чтение первого листа Excel файла
    try:
        df = pd.read_excel(file_path, sheet_name=0, engine='openpyxl')

        if df.empty:
            print(f"Файл {file_path} пуст или не содержит данных.")
            return

        # Проверка соответствия полей Excel-файла и полей originalName в JSON-файле
        original_names = [item['originalName'] for item in schema_manifest]
        if not set(df.columns).issubset(set(original_names)):
            with open('reading.log', 'a') as log_file:
                log_file.write(f"Файл {file_path} содержит несоответствующие поля и будет пропущен.\n")
            print(f"Файл {file_path} содержит несоответствующие поля и будет пропущен.")
            return

        # Преобразование данных в соответствии со схемой
        timestamp_columns = [item['originalName'] for item in schema_manifest if item['datatype'] == 'timestamp']
        for col in timestamp_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')

        # Удаление символов новой строки из всех полей DataFrame
        df = df.apply(lambda x: x.map(lambda y: ' '.join(str(y).splitlines())) if x.dtype == 'object' else x)

        # Добавляем столбцы dtflow, dt_file_create и file_name
        df['dtflow'] = dtflow
        df['dt_file_create'] = dtcreate
        df['file_name'] = os.path.basename(file_path)

        # Преобразуем и очищаем поле hscode
        if 'hscode' in df.columns:
            df['hscode'] = df['hscode'].astype(str).replace('nan', '')

        # Записываем данные в базу данных
        write_to_db(df, dtcreate, os.path.basename(file_path))
    except Exception as e:
        print(f"Ошибка при обработке файла {file_path}: {e}")

# Функция для поиска последних трех файлов, соответствующих схеме
def find_last_three_valid_files(directory, schema_manifest):
    valid_files = []
    all_files = []

    # Сканируем папку и собираем файлы Excel с датой создания
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.xlsx'):
                file_path = os.path.join(root, file)
                creation_time = os.path.getctime(file_path)
                all_files.append((file_path, creation_time))

    # Сортируем все файлы по дате создания (от нового к старому)
    sorted_files = sorted(all_files, key=lambda x: x[1], reverse=True)

    # Проверяем каждый файл на соответствие схеме
    for file_path, _ in sorted_files:
        try:
            df = pd.read_excel(file_path, sheet_name=0, engine='openpyxl')
            if df.empty:
                continue  # Пропускаем пустые файлы

            # Проверка соответствия колонок схеме
            original_names = [item['originalName'] for item in schema_manifest]
            if set(df.columns).issubset(set(original_names)):
                valid_files.append(file_path)
            
            # Если набрано три файла, прерываем цикл
            if len(valid_files) == 3:
                break
        except Exception as e:
            print(f"Ошибка при чтении файла {file_path}: {e}")
            continue

    return valid_files

# Поиск и обработка последних трех валидных файлов
last_valid_files = find_last_three_valid_files(manifest_dir, schema_manifest)

for file in last_valid_files:
    process_excel_file(file)

# Время завершения выполнения скрипта
end_time = time.time()

# Вывод времени выполнения и количества обработанных файлов
execution_time = end_time - start_time
print(f"Время выполнения скрипта: {execution_time:.2f} секунд")
print(f"Количество обработанных файлов: {len(last_valid_files)}")
