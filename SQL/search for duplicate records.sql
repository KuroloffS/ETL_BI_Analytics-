WITH cte AS (
    SELECT 
        id,
        ROW_NUMBER() OVER (PARTITION BY itemid ORDER BY id) AS rn
    FROM manifest
)
DELETE FROM manifest
WHERE id IN (
    SELECT id
    FROM cte
    WHERE rn > 1
);
