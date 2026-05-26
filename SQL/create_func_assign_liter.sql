CREATE OR REPLACE FUNCTION assign_liter(weight_g BIGINT) RETURNS CHAR AS $$
BEGIN
    RETURN CASE
        WHEN weight_g BETWEEN 0 AND 20 THEN 'A'
        WHEN weight_g BETWEEN 21 AND 60 THEN 'B'
        WHEN weight_g BETWEEN 61 AND 100 THEN 'C'
        WHEN weight_g BETWEEN 101 AND 200 THEN 'D'
        WHEN weight_g BETWEEN 201 AND 400 THEN 'E'
        WHEN weight_g BETWEEN 401 AND 600 THEN 'F'
        ELSE 'G'
    END;
END;
$$ LANGUAGE plpgsql;