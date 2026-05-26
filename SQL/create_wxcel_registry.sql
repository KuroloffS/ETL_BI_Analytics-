CREATE TABLE Excel_registry (
    id SERIAL PRIMARY KEY,  -- Уникальный идентификатор записи
    target_folder TEXT NOT NULL,
    file_name TEXT NOT NULL,
    dt_create TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    size_Kb INT NOT NULL,
    dtflow TIMESTAMP WITHOUT TIME ZONE NOT NULL
);
