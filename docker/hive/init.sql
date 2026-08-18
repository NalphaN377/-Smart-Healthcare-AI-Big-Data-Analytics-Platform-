CREATE DATABASE IF NOT EXISTS medical_analytics
LOCATION 'hdfs://namenode:8020/medical/warehouse/medical_analytics.db';

CREATE EXTERNAL TABLE IF NOT EXISTS medical_analytics.hospital_discharges (
  hospital_service_area STRING,
  hospital_county STRING,
  operating_certificate_number STRING,
  facility_id BIGINT,
  facility_name STRING,
  age_group STRING,
  zip_code_3_digits STRING,
  gender STRING,
  race STRING,
  ethnicity STRING,
  length_of_stay_raw STRING,
  length_of_stay BIGINT,
  admission_type STRING,
  patient_disposition STRING,
  discharge_year BIGINT,
  diagnosis_code STRING,
  diagnosis_description STRING,
  procedure_code STRING,
  procedure_description STRING,
  apr_drg_code BIGINT,
  apr_drg_description STRING,
  apr_mdc_code BIGINT,
  apr_mdc_description STRING,
  severity_code BIGINT,
  severity STRING,
  mortality_risk STRING,
  medical_surgical_description STRING,
  payment_type_1 STRING,
  payment_type_2 STRING,
  payment_type_3 STRING,
  birth_weight BIGINT,
  emergency_indicator BOOLEAN,
  total_charges DOUBLE,
  total_costs DOUBLE,
  source_file STRING,
  source_row_number BIGINT,
  record_hash STRING
)
STORED AS PARQUET
LOCATION 'hdfs://namenode:8020/medical/processed/hospital_discharges'
TBLPROPERTIES ('external.table.purge'='false');
