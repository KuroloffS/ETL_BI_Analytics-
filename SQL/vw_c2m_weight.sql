CREATE OR REPLACE VIEW vw_c2m_weight AS
WITH liter_assignment AS (
         SELECT c2m_logistic.dt_package,
            c2m_logistic.package_num,
            c2m_logistic.country,
            c2m_logistic.service,
            c2m_logistic.weight_g,
            assign_liter(c2m_logistic.weight_g::numeric) AS liter,
            calc_roundup_weight(c2m_logistic.weight_g::numeric) AS excel_weight
           FROM c2m_logistic
        ), summarized_data AS (
         SELECT liter_assignment.dt_package,
            liter_assignment.package_num,
            liter_assignment.country,
            liter_assignment.service,
            liter_assignment.liter,
            count(*) AS count_records,
            sum(liter_assignment.weight_g) AS weight_g,
            sum(liter_assignment.excel_weight) AS weight_kg
           FROM liter_assignment
          GROUP BY liter_assignment.dt_package, liter_assignment.package_num, liter_assignment.country, liter_assignment.service, liter_assignment.liter
        )
 SELECT dt_package,
    package_num,
    country,
    service,
    liter,
    weight_g,
    count_records,
    weight_g / count_records::numeric AS average_weight,
    weight_kg
   FROM summarized_data;
