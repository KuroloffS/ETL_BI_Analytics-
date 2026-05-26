import psycopg2
from psycopg2 import sql


def upsert_data(cursor, connect, data, table_name, schema):
    """
    Вставляет или обновляет данные в таблице PostgreSQL (upsert).

    :param connect: Соединение с базой данных PostgreSQL.
    :param table_name: Название таблицы для вставки данных.
    :param data: Список словарей, представляющих данные для вставки или обновления.
    :param schema: Список словарей с описанием структуры таблицы.
                   Пример: [{"db_name": "itemid", "datatype": "TEXT"}, {"db_name": "name", "datatype": "TEXT"}].
    """
    try:

        # Генерация SQL для создания таблицы
        columns_definitions = ', '.join([f"{col['db_name']} {col['datatype']}" for col in schema])
        unique_key = schema[0]['db_name']  # Предполагается, что первый столбец — уникальный

        # Используем sql.SQL для создания корректного запроса
        create_table_query = sql.SQL("""
        CREATE TABLE IF NOT EXISTS {table} (
            id SERIAL PRIMARY KEY,
            {columns_definitions},
            UNIQUE ({unique_key})
        );
        """).format(
        table=sql.Identifier('public', table_name),  # имя таблицы в схеме 'public'
        columns_definitions=sql.SQL(columns_definitions),  # определения колонок
        unique_key=sql.Identifier(unique_key)  # уникальный ключ
        )

        # Выполнение запроса
        cursor.execute(create_table_query)
        connect.commit()
        
        # Подготовка запроса INSERT с ON CONFLICT
        columns = [col['db_name'] for col in schema]
        insert_query = sql.SQL("""
        INSERT INTO {table} ({columns})
        VALUES ({placeholders})
        ON CONFLICT ({unique_key}) DO UPDATE
        SET {updates};
        """).format(
            table=sql.Identifier(table_name),
            columns=sql.SQL(', ').join(map(sql.Identifier, columns)),
            placeholders=sql.SQL(', ').join(sql.Placeholder() for _ in columns),
            unique_key=sql.Identifier(unique_key),
            updates=sql.SQL(', ').join(
                sql.SQL(f"{col} = EXCLUDED.{col}") for col in columns if col != unique_key
            )
        )

        # Выполнение вставки для каждой записи
        for record in data:
            values = [record[col] for col in columns]
            cursor.execute(insert_query, values)

        connect.commit()

        print(f"Данные успешно обработаны и записаны в таблицу {table_name}.")
    except Exception as e:
        print(f"Ошибка выполнения upsert операции: {e}")
        if connect:
            connect.rollback()
        raise
