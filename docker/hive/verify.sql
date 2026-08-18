USE medical_analytics;

SELECT COUNT(*) AS record_count,
       COUNT(DISTINCT CASE
         WHEN facility_name IS NOT NULL AND TRIM(facility_name) <> ''
         THEN TRIM(facility_name)
       END) AS facility_count
FROM hospital_discharges;

SELECT diagnosis_description, COUNT(*) AS record_count
FROM hospital_discharges
WHERE diagnosis_description IS NOT NULL AND TRIM(diagnosis_description) <> ''
GROUP BY diagnosis_description
ORDER BY record_count DESC, diagnosis_description ASC
LIMIT 10;

SELECT AVG(total_charges) AS avg_total_charges,
       AVG(total_costs) AS avg_total_costs,
       AVG(length_of_stay) AS avg_length_of_stay
FROM hospital_discharges;

SELECT payment_type_1, COUNT(*) AS record_count
FROM hospital_discharges
WHERE payment_type_1 IS NOT NULL AND TRIM(payment_type_1) <> ''
GROUP BY payment_type_1
ORDER BY record_count DESC, payment_type_1 ASC;

SELECT severity, COUNT(*) AS record_count,
       AVG(total_charges) AS avg_total_charges,
       AVG(length_of_stay) AS avg_length_of_stay
FROM hospital_discharges
WHERE severity IS NOT NULL AND TRIM(severity) <> ''
GROUP BY severity
ORDER BY record_count DESC, severity ASC;
