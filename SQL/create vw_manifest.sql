CREATE VIEW vw_manifest AS
WITH manifest_manual_aggregated AS (
    SELECT 
        package_date AS date,
        country,
        service,
        CAST(package_num AS character varying) AS package_num, -- Преобразование типа
        liter,
        tariff_per_item,
        tariff_per_kg,
        COUNT(itemid) AS qty,
        SUM(productweight_kg) AS weight_kg,
        SUM(total_for_kg) AS tariff_for_kg,
        SUM(total) AS total_tariff,
        CASE
            WHEN service = 'SRMDG' THEN 'dangerous'
            ELSE 'general'
        END AS danger_type
    FROM manifest_manual
    WHERE country NOT IN ('GE', 'AM', 'MD')
    GROUP BY 
        package_date, country, service, package_num, liter, tariff_per_item, tariff_per_kg
),
manifest_aggregated AS (
    WITH liter_assignment AS (
        SELECT 
            m.dt_package AS date,
            CAST(m.package_num AS character varying) AS package_num, -- Преобразование типа
            m.country,
            m.service,
            m.weight_g,
            assign_liter(m.weight_g::numeric) AS liter,
            calc_roundup_weight(m.weight_g::numeric) AS excel_weight,
            m.danger_type
        FROM manifest m
    ), 
    summarized_data AS (
        SELECT 
            liter_assignment.date,
            liter_assignment.package_num,
            liter_assignment.country,
            liter_assignment.service,
            liter_assignment.liter,
            liter_assignment.danger_type,
            COUNT(*) AS count_records,
            SUM(liter_assignment.weight_g) AS weight_g,
            SUM(liter_assignment.excel_weight) AS weight_kg
        FROM liter_assignment
        GROUP BY 
            liter_assignment.date, 
            liter_assignment.package_num, 
            liter_assignment.country, 
            liter_assignment.service, 
            liter_assignment.liter, 
            liter_assignment.danger_type
    )
    SELECT 
        date,
        country,
        service,
        package_num,
        liter,
        CAST(NULL AS double precision) AS tariff_per_item, -- Приведение к double precision
        CAST(NULL AS double precision) AS tariff_per_kg,   -- Приведение к double precision
        count_records AS qty,
        weight_kg,
        CAST(NULL AS double precision) AS tariff_for_kg,   -- Приведение к double precision
        CAST(NULL AS double precision) AS total_tariff,    -- Приведение к double precision
        danger_type
    FROM summarized_data
    WHERE 
        service NOT IN ('UZC', 'UZUM') 
        AND country NOT IN ('GE', 'AM', 'MD') 
        AND date >= '2024-12-01'
)
SELECT * 
FROM manifest_manual_aggregated
WHERE date < '2024-12-01'

UNION ALL

SELECT * 
FROM manifest_aggregated
WHERE date >= '2024-12-01';
