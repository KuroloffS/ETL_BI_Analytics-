
select * from public.manifest

-- delete from public.excel_registry where 
-- truncate table public.manifest

select * from public.excel_registry where dt_processed is null
select * from public.c2m_logistic where packageweight_g > 0 limit 1000


UPDATE public.excel_registry SET dt_processed = NULL;


-- truncate table public.c2m_temp
-- truncate table public.excel_reg_temp

CREATE TABLE c2m_temp AS TABLE manifest WITH NO DATA
ALTER TABLE public.excel_registry  RENAME COLUMN error_massage TO error_message
ALTER TABLE public.excel_reg_temp
ALTER TABLE public.c2m_logistic ADD COLUMN id_registry BIGINT

ALTER TABLE c2m_temp ALTER COLUMN parceledirecvdate TYPE timestamp without time zone USING parceledirecvdate::timestamp without time zone;

select * from public.c2m_temp -- where packageweight_g > 0
select * from public.cainiao_for_dm

ALTER TABLE public.excel_registry
ALTER COLUMN dt_package TYPE DATE USING dt_package::DATE;

INSERT INTO public.excel_reg_temp SELECT * FROM public.excel_registry LIMIT 5

CREATE TABLE public.excel_reg_temp AS TABLE public.excel_registry WITH NO DATA
CREATE TABLE public.c2m_logistics AS TABLE public.c2m_temp WITH NO DATA
CREATE UNIQUE INDEX c2m_logistics_with_itemid ON public.c2m_logistics(itemid);
CREATE UNIQUE INDEX c2m_temp_with_itemid ON public.c2m_temp(itemid);

SELECT update_excel_registry();
-------------------------------------------
select count(*) from public.manifest_manual 
WHERE EXTRACT(YEAR FROM package_date) = 2024
  AND EXTRACT(MONTH FROM package_date) = 11;
--truncate table manifest_manual 

CREATE TABLE manual_report (
    cartonid VARCHAR(50),
    itemid VARCHAR(50),
    ordercode VARCHAR(50),
    productweight_g BIGINT,
    productweight_kg FLOAT,
    tariff_per_kg FLOAT,
    tariff_per_item FLOAT,
    total_for_kg FLOAT,
    total FLOAT,
    country VARCHAR(50),
    service VARCHAR(50),
    liter VARCHAR(50),
    service_country VARCHAR(50),
    package_num INTEGER,
    package_date DATE
);
ALTER TABLE manual_report
RENAME TO manifest_manual;

SELECT 
package_date,
package_num,
country,
service,
liter,
SUM(productweight_kg) AS weight_kg
FROM manifest_manual
GROUP BY 1,2,3,4,5



