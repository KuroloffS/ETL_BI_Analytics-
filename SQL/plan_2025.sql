WITH MaxDateTariffs AS (
    SELECT 
        Country, 
        Service, 
        tariff_range,
        MAX(DateFrom) AS MaxDateFrom
    FROM tariff
    GROUP BY Country, Service, tariff_range
),
FilteredTariffs AS (
    SELECT 
        t.Country,
        t.Service,
        t.tariff_range,
        t.PER_KG,
        t.PER_ITEM,
        m.MaxDateFrom
    FROM tariff t
    INNER JOIN MaxDateTariffs m
        ON t.Country = m.Country 
        AND t.Service = m.Service 
        AND t.tariff_range = m.tariff_range 
        AND t.DateFrom = m.MaxDateFrom
),
Result AS (
    SELECT 
        p.country,
        p.service,
        p.item,
        p.tariff_range,
        p.Value,
        p.period,
        p.Linehall,
        CASE 
            WHEN p.item = 'кг' THEN ft.PER_KG
            WHEN p.item = 'шт' THEN ft.PER_ITEM
            ELSE NULL
        END AS tariff
    FROM c2m_plan_2025 p
    LEFT JOIN FilteredTariffs ft
        ON p.country = ft.Country 
        AND p.service = ft.Service
        AND p.tariff_range = ft.tariff_range
        AND p.period >= ft.MaxDateFrom
)
SELECT distinct * FROM Result ORDER BY period;

