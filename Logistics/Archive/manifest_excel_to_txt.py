import os
import pandas as pd
from datetime import datetime
import time
from dotenv import load_dotenv

# Загрузить переменные из .env файла
load_dotenv()

db_name = os.getenv('DB_NAME')
db_host = os.getenv('DB_HOST')
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')

# Путь к папке с файлами
manifest_dir = '//10.1.19.245/C2M Logistics/тест'

# Массив для хранения данных
data_list = []
processed_files = 0  # Счетчик обработанных файлов
total_rows = 0       # Счетчик общего количества строк

# Текущая дата и время для поля dtflow
dtflow = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# Время начала выполнения скрипта
start_time = time.time()

# Функция для обхода всех файлов и папок в директории
def process_directory(directory):
    global processed_files
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.xlsx'):
                file_path = os.path.join(root, file)
                process_excel_file(file_path)
                processed_files += 1  # Увеличиваем счетчик обработанных файлов
                print(f"Успешно прочитан файл: {file_path}")

# Функция для обработки одного Excel файла
def process_excel_file(file_path):
    global total_rows
    # Дата создания файла
    dtcreate = datetime.fromtimestamp(os.path.getctime(file_path)).strftime('%Y-%m-%d %H:%M:%S')

    # Чтение первого листа Excel файла
    try:
        # Чтение данных с первого листа
        df = pd.read_excel(file_path, sheet_name=0, engine='openpyxl')

        # Проверка, что данные действительно считались корректно
        if df.empty:
            print(f"Файл {file_path} пуст или не содержит данных.")
            return

        # Пример преобразования даты в нужный формат в определённых столбцах
        date_columns = ['parceledirecvdate', 'bigbagrecvdate']  # Здесь укажите названия колонок с датами
        for col in date_columns:
            if col in df.columns:
                # Преобразование строки с датами в формат дд.мм.гггг чч:мм:сс
                df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%d.%m.%Y %H:%M:%S')

        # Преобразование чисел с точками на числа с запятыми только для числовых столбцов
        for col in df.select_dtypes(include=['float', 'int']).columns:
            df[col] = df[col].map(lambda x: str(x).replace('.', ','))

        # Удаление символов новой строки (LF) из всех полей DataFrame
        df = df.apply(lambda x: x.map(lambda y: ' '.join(str(y).splitlines())) if x.dtype == 'object' else x)

        # Добавляем столбцы dtflow и dtcreate
        df['dtflow'] = dtflow
        df['dtcreate'] = dtcreate

        # Удаляем столбец consigneeaddress
        if 'consigneeaddress' in df.columns:
            df = df.drop(columns=['consigneeaddress'])

        # Добавляем данные в общий массив
        data_list.append(df)

        # Увеличиваем счетчик общего количества строк
        total_rows += len(df)
    except Exception as e:
        print(f"Ошибка при обработке файла {file_path}: {e}")

# Обход всех файлов в папке manifest
process_directory(manifest_dir)

# Сохраняем все данные в CSV
if data_list:
    # Конкатенируем все таблицы в один DataFrame
    combined_df = pd.concat(data_list, ignore_index=True)

    # Записываем в CSV файл с указанием разделителя ";"
    combined_df.to_csv('manifest.csv', index=False, sep=';', encoding='utf-8-sig')

    print(f"Данные успешно записаны в manifest.csv")
else:
    print("Нет данных для записи в manifest.csv")

# Время завершения выполнения скрипта
end_time = time.time()

# Вывод времени выполнения, количества файлов и строк
execution_time = end_time - start_time
print(f"Время выполнения скрипта: {execution_time:.2f} секунд")
print(f"Количество обработанных файлов: {processed_files}")
print(f"Общее количество строк, записанных в CSV: {total_rows}")