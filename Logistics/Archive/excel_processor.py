import pandas as pd
import numpy as np
import logging
import os

# Настройка логирования
logging.basicConfig(filename='excel_processor.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def prepare_data(file_name, schema):
    """Обрабатывает список файлов Excel и возвращает список словарей для записи в базу данных."""

    if not os.path.exists(file_name):   # проверяем наличие файла по указанному адресу
        print(f"Файл {file_name} не найден.")
        return None
    
    # Создаем словари для типов данных и переименования столбцов
    dtype_map = {}
    rename_map = {}
    for item in schema:
        original_name = item['originalName']
        db_name = item['db_name']
        datatype = item['datatype']
        
        dtype_map[original_name] = datatype
        rename_map[original_name] = db_name
   
    df = pd.DataFrame()
    
    try:
        try:
            raw_df = pd.read_excel(file_name, sheet_name=0, engine='openpyxl')
            print(f"[DEBUG] Columns in the file: {list(raw_df.columns)}")
        except Exception as e:
            print(f"[ERROR] Ошибка при чтении Excel-файла: {e}")
            return None

        df = pd.read_excel(file_name, sheet_name=0, engine='openpyxl', usecols=dtype_map.keys(), dtype=dtype_map)
        df.rename(columns=rename_map, inplace=True)
            
        # Преобразуем пустые значения в None
        df = df.replace({np.nan: None})
            
        logging.info(f"Processed file: {file_name}")
    except Exception as e:
        logging.error(f"Failed to process file {file_name}: {e}")
        
    return df

