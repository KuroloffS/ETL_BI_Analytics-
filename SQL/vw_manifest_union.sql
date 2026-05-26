CREATE VIEW vw_manifest_union AS
SELECT
    package_date AS dt_package,
    package_num::text, -- Приведение к типу text
    country,
    service,
    liter,
    COUNT(itemid) AS count_records,
    SUM(productweight_kg) AS weight_kg,
    CASE
        WHEN service::text = 'SRMDG' THEN 'Dangerous'
        ELSE 'General'
    END AS danger_type,
    tariff_per_item AS per_item,
    tariff_per_kg AS per_kg
FROM
    manifest_manual
WHERE
    country::text NOT IN ('GE', 'AM', 'MD') -- Упрощенное условие
GROUP BY
    package_date,
    package_num, -- Группировка по package_num (теперь он приведен к text)
    country,
    service,
    liter,
    tariff_per_item,
    tariff_per_kg

UNION

SELECT
    dt_package,
    package_num::text, -- Приведение к типу text
    country,
    service,
    liter,
    count_records,
    weight_kg,
    danger_type,
    per_item,
    per_kg
FROM
    public.vw_c2m_manifest;