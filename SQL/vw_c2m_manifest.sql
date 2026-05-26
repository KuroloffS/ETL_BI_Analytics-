CREATE VIEW vw_c2m_manifest AS
WITH tariff_data AS (
    SELECT
        t.per_kg,
        t.per_item,
        t.tariff_range,
        t.datefrom,
        t.liter,
        t.service,
        t.country,
        ROW_NUMBER() OVER (
            PARTITION BY t.liter, t.service, t.country
            ORDER BY t.datefrom DESC
        ) AS rn
    FROM
        tariff t
)
SELECT
    m.dt_package,
    m.package_num,
    m.country,
    m.service,
    assign_liter(m.weight_g::numeric) AS liter,
    SUM(m.weight_g) AS weight_g,
    COUNT(m.itemid) AS count_records,
    SUM(m.weight_g) / COUNT(m.itemid)::numeric AS average_weight,
    SUM(calc_roundup_weight(m.weight_g::numeric)) AS weight_kg,
    CASE
        WHEN m.service = 'SRMDG' THEN 'Dangerous'
        ELSE 'General'
    END AS danger_type,
    td.per_kg,
    td.per_item,
    td.tariff_range
FROM
    manifest m
LEFT JOIN tariff_data td
    ON td.liter = assign_liter(m.weight_g::numeric)
    AND td.service = m.service
    AND td.country = m.country
    AND td.datefrom <= m.dt_package
    AND td.rn = 1 -- Выбираем только одну строку с максимальной датой
WHERE
    m.service::text NOT IN ('UZC', 'UZUM') -- Фильтр по service
    AND m.country::text NOT IN ('GE', 'AM', 'MD') -- Фильтр по country
    AND m.dt_package >= '2024-12-01' -- Фильтр по дате
GROUP BY
    m.dt_package,
    m.package_num,
    m.country,
    m.service,
    assign_liter(m.weight_g::numeric),
    td.per_kg,
    td.per_item,
    td.tariff_range;