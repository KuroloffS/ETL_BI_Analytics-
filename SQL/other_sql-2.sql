CREATE VIEW vw_c2m_manifest AS
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
    END AS danger_type
FROM
    manifest m
WHERE
    m.service::text NOT IN ('UZC', 'UZUM') -- Фильтр по service
    AND m.country::text NOT IN ('GE', 'AM', 'MD') -- Фильтр по country
    AND m.dt_package >= '2024-12-01' -- Фильтр по дате
GROUP BY
    m.dt_package,
    m.package_num,
    m.country,
    m.service,
    assign_liter(m.weight_g::numeric); -- Группировка по вычисляемому полю