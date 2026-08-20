-- 智慧医疗大数据平台 - SQL Server 2019+ Schema
-- 目标数据库由 DB_NAME 指定；脚本不会删除已有数据。

SET NOCOUNT ON;
GO

IF OBJECT_ID(N'dbo.inpatient_discharge_stage', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.inpatient_discharge_stage (
        hospital_service_area NVARCHAR(500) NULL,
        hospital_county NVARCHAR(500) NULL,
        operating_certificate_number NVARCHAR(500) NULL,
        permanent_facility_id NVARCHAR(500) NULL,
        facility_name NVARCHAR(500) NULL,
        age_group NVARCHAR(500) NULL,
        zip_code_3 NVARCHAR(500) NULL,
        gender NVARCHAR(500) NULL,
        race NVARCHAR(500) NULL,
        ethnicity NVARCHAR(500) NULL,
        length_of_stay NVARCHAR(500) NULL,
        type_of_admission NVARCHAR(500) NULL,
        patient_disposition NVARCHAR(500) NULL,
        discharge_year NVARCHAR(500) NULL,
        ccsr_diagnosis_code NVARCHAR(500) NULL,
        ccsr_diagnosis_description NVARCHAR(500) NULL,
        ccsr_procedure_code NVARCHAR(500) NULL,
        ccsr_procedure_description NVARCHAR(500) NULL,
        apr_drg_code NVARCHAR(500) NULL,
        apr_drg_description NVARCHAR(500) NULL,
        apr_mdc_code NVARCHAR(500) NULL,
        apr_mdc_description NVARCHAR(500) NULL,
        apr_severity_of_illness_code NVARCHAR(500) NULL,
        apr_severity_of_illness_desc NVARCHAR(500) NULL,
        apr_risk_of_mortality NVARCHAR(500) NULL,
        apr_medical_surgical_desc NVARCHAR(500) NULL,
        payment_typology_1 NVARCHAR(500) NULL,
        payment_typology_2 NVARCHAR(500) NULL,
        payment_typology_3 NVARCHAR(500) NULL,
        birth_weight NVARCHAR(500) NULL,
        emergency_department_indicator NVARCHAR(500) NULL,
        total_charges NVARCHAR(500) NULL,
        total_costs NVARCHAR(500) NULL
    );
END;
GO

IF OBJECT_ID(N'dbo.inpatient_discharge', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.inpatient_discharge (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT pk_inpatient_discharge PRIMARY KEY,
        hospital_service_area NVARCHAR(100) NULL,
        hospital_county NVARCHAR(100) NULL,
        operating_certificate_number NVARCHAR(20) NULL,
        permanent_facility_id NVARCHAR(20) NULL,
        facility_name NVARCHAR(200) NULL,
        age_group NVARCHAR(20) NULL,
        zip_code_3 NVARCHAR(10) NULL,
        gender NCHAR(1) NULL,
        race NVARCHAR(50) NULL,
        ethnicity NVARCHAR(50) NULL,
        length_of_stay INT NULL,
        type_of_admission NVARCHAR(50) NULL,
        patient_disposition NVARCHAR(120) NULL,
        discharge_year SMALLINT NULL,
        ccsr_diagnosis_code NVARCHAR(20) NULL,
        ccsr_diagnosis_description NVARCHAR(300) NULL,
        ccsr_procedure_code NVARCHAR(20) NULL,
        ccsr_procedure_description NVARCHAR(300) NULL,
        apr_drg_code NVARCHAR(20) NULL,
        apr_drg_description NVARCHAR(300) NULL,
        apr_mdc_code NVARCHAR(10) NULL,
        apr_mdc_description NVARCHAR(300) NULL,
        apr_severity_of_illness_code TINYINT NULL,
        apr_severity_of_illness_desc NVARCHAR(50) NULL,
        apr_risk_of_mortality NVARCHAR(20) NULL,
        apr_medical_surgical_desc NVARCHAR(30) NULL,
        payment_typology_1 NVARCHAR(60) NULL,
        payment_typology_2 NVARCHAR(60) NULL,
        payment_typology_3 NVARCHAR(60) NULL,
        birth_weight NVARCHAR(10) NULL,
        emergency_department_indicator NCHAR(1) NULL,
        total_charges DECIMAL(14,2) NULL,
        total_costs DECIMAL(14,2) NULL,
        source_row_hash BINARY(32) NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT df_inpatient_created_at DEFAULT SYSUTCDATETIME()
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.inpatient_discharge') AND name=N'idx_discharge_year')
    CREATE INDEX idx_discharge_year ON dbo.inpatient_discharge(discharge_year);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.inpatient_discharge') AND name=N'idx_ccsr_diagnosis')
    CREATE INDEX idx_ccsr_diagnosis ON dbo.inpatient_discharge(ccsr_diagnosis_code) INCLUDE(ccsr_diagnosis_description);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.inpatient_discharge') AND name=N'idx_facility')
    CREATE INDEX idx_facility ON dbo.inpatient_discharge(facility_name);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.inpatient_discharge') AND name=N'idx_service_area')
    CREATE INDEX idx_service_area ON dbo.inpatient_discharge(hospital_service_area);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.inpatient_discharge') AND name=N'idx_age_group')
    CREATE INDEX idx_age_group ON dbo.inpatient_discharge(age_group);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.inpatient_discharge') AND name=N'idx_payment')
    CREATE INDEX idx_payment ON dbo.inpatient_discharge(payment_typology_1);
GO

IF OBJECT_ID(N'dbo.ingestion_run', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ingestion_run (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT pk_ingestion_run PRIMARY KEY,
        source_file NVARCHAR(500) NOT NULL,
        source_size_bytes BIGINT NULL,
        started_at DATETIME2(0) NOT NULL CONSTRAINT df_ingestion_started DEFAULT SYSUTCDATETIME(),
        finished_at DATETIME2(0) NULL,
        status NVARCHAR(20) NOT NULL,
        chunks_processed INT NOT NULL CONSTRAINT df_ingestion_chunks DEFAULT 0,
        rows_read BIGINT NOT NULL CONSTRAINT df_ingestion_read DEFAULT 0,
        rows_inserted BIGINT NOT NULL CONSTRAINT df_ingestion_inserted DEFAULT 0,
        rows_dropped BIGINT NOT NULL CONSTRAINT df_ingestion_dropped DEFAULT 0,
        quality_json NVARCHAR(MAX) NULL,
        error_message NVARCHAR(2000) NULL
    );
END;
GO
