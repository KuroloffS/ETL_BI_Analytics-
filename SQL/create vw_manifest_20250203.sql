CREATE VIEW vw_manifest_20250203 AS
SELECT
    m.dt_package,
    m.package_num,
    m.country,
    CASE
        WHEN m.danger_type = 'BatteryAir' THEN m.service || 'DG'
        ELSE m.service
    END AS service,
    assign_liter(m.weight_g::numeric) AS liter,
    SUM(m.weight_g) AS weight_g,
    COUNT(m.itemid) AS count_records,
    SUM(m.weight_g) / COUNT(m.itemid)::numeric AS average_weight,
    SUM(calc_roundup_weight(m.weight_g::numeric)) AS weight_kg,
    CASE
        WHEN m.danger_type = 'General' THEN 'General'
        ELSE 'Dangerous'
    END AS danger_type,
    td.per_kg,
    td.per_item,
    td.tariff_range
FROM manifest m
LEFT JOIN LATERAL (
    SELECT t.per_kg, t.per_item, t.tariff_range
    FROM tariff t
    WHERE t.datefrom <= m.dt_package
      AND t.liter = assign_liter(m.weight_g::numeric)
      AND t.country = m.country
      AND t.service = CASE
                         WHEN m.danger_type = 'BatteryAir' THEN m.service || 'DG'
                         ELSE m.service
                     END
    ORDER BY t.datefrom DESC
    LIMIT 1
) td ON TRUE
WHERE m.service NOT IN ('UZC', 'UZUM')
  AND m.country NOT IN ('GE', 'AM', 'MD')
  AND m.dt_package >= '2024-12-01'
GROUP BY
    m.dt_package,
    m.package_num,
    m.country,
    service,
    liter,
    m.danger_type,
    td.per_kg,
    td.per_item,
    td.tariff_range;


