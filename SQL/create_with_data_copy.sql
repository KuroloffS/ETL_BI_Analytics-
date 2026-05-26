-- Параметры
DO $$
DECLARE
    src_table text := 'excel_registry'; 	-- Имя существующей таблицы
    dest_table text := 'excel_reg_temp';   -- Имя создаваемой таблицы
    row_limit int := 5;                	-- Количество строк для копирования
BEGIN
    -- Создать новую таблицу с той же структурой, что и у существующей
    EXECUTE format(
        'CREATE TABLE %I AS TABLE %I WITH NO DATA',
        dest_table, src_table
    );

    -- Скопировать первые 10 строк из существующей таблицы в новую
    EXECUTE format(
        'INSERT INTO %I SELECT * FROM %I LIMIT %s',
        dest_table, src_table, row_limit
    );

    RAISE NOTICE 'Таблица % создана и заполнена % строками из таблицы %.', dest_table, row_limit, src_table;
END $$;
