import os
import pandas as pd
from datetime import datetime
import time
import re  # Для работы с регулярными выражениями

# Путь к папке с файлами
manifest_dir = './manifest_data'
# manifest_dir = './temp'

# Массив для хранения данных
data_list = []
processed_files = 0  # Счетчик обработанных файлов
total_rows = 0       # Счетчик общего количества строк

# Текущая дата и время для поля dtflow
dtflow = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# Время начала выполнения скрипта
start_time = time.time()

# Список необходимых полей в нижнем регистре
required_columns = [
    'parceledirecvdate',
    'bigbagrecvdate',
    'consigneecountry',
    'value',
    'service',
    'dtflow',
    'dtcreate',
    'packageweight(g)'
]

# Функция для очистки имен колонок
def clean_column_names(columns):
    cleaned_columns = []
    for col in columns:
        # Приведение к нижнему регистру, удаление переносов строк и лишних пробелов
        cleaned_col = col.strip().replace('\n', '').lower()
        cleaned_columns.append(cleaned_col)
    return cleaned_columns

# Функция для поиска и корректной обработки поля 'value'
def find_value_column(df_columns):
    for col in df_columns:
        if 'value' in col.lower():
            return col  # Возвращаем первое вхождение, где есть 'value'
    return None

# Функция для обхода всех файлов и папок в директории
def process_directory(directory):
    global processed_files
    for root, dirs, files in os.walk(directory):
        # Проверка наличия подпапки Manifest
        if 'Manifest' not in root.split(os.sep):
            continue
        for file in files:
            if file.endswith('.xlsx'):
                file_path = os.path.join(root, file)
                # Проверка размера файла (больше 500 КБ)
                if os.path.getsize(file_path) > 500 * 1024:
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

        # Приведение всех имен колонок к нижнему регистру и их очистка
        df.columns = clean_column_names(df.columns)

        # Переименование колонки 'productweight(g)' в 'packageweight(g)'
        if 'productweight(g)' in df.columns:
            df.rename(columns={'productweight(g)': 'packageweight(g)'}, inplace=True)

        # Поиск и замена колонки 'value'
        value_column = find_value_column(df.columns)
        if value_column:
            df.rename(columns={value_column: 'value'}, inplace=True)

        # Пример преобразования даты в нужный формат в определённых столбцах
        date_columns = ['parceledirecvdate', 'bigbagrecvdate']
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

        # Фильтрация колонок для соответствия требуемым полям
        df_filtered = df[[col for col in required_columns if col in df.columns]]

        # Добавляем данные в общий массив
        data_list.append(df_filtered)

        # Увеличиваем счетчик общего количества строк
        total_rows += len(df_filtered)
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