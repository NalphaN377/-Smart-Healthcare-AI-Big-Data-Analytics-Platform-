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

IF COL_LENGTH(N'dbo.inpatient_discharge', N'source_row_hash') IS NULL
    ALTER TABLE dbo.inpatient_discharge ADD source_row_hash BINARY(32) NULL;
IF COL_LENGTH(N'dbo.inpatient_discharge', N'source_batch_id') IS NULL
    ALTER TABLE dbo.inpatient_discharge ADD source_batch_id BIGINT NULL;
IF COL_LENGTH(N'dbo.inpatient_discharge', N'created_at') IS NULL
    ALTER TABLE dbo.inpatient_discharge ADD created_at DATETIME2(0) NULL CONSTRAINT df_inpatient_created_at_migration DEFAULT SYSUTCDATETIME();
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
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.inpatient_discharge') AND name=N'ux_inpatient_source_row_hash')
    CREATE UNIQUE INDEX ux_inpatient_source_row_hash ON dbo.inpatient_discharge(source_row_hash) WHERE source_row_hash IS NOT NULL;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.inpatient_discharge') AND name=N'idx_inpatient_source_batch')
    CREATE INDEX idx_inpatient_source_batch ON dbo.inpatient_discharge(source_batch_id) WHERE source_batch_id IS NOT NULL;
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

IF COL_LENGTH(N'dbo.ingestion_run', N'source_sha256') IS NULL
    ALTER TABLE dbo.ingestion_run ADD source_sha256 CHAR(64) NULL;
IF COL_LENGTH(N'dbo.ingestion_run', N'ingestion_mode') IS NULL
    ALTER TABLE dbo.ingestion_run ADD ingestion_mode NVARCHAR(20) NOT NULL CONSTRAINT df_ingestion_mode DEFAULT 'full';
IF COL_LENGTH(N'dbo.ingestion_run', N'rows_skipped') IS NULL
    ALTER TABLE dbo.ingestion_run ADD rows_skipped BIGINT NOT NULL CONSTRAINT df_ingestion_skipped DEFAULT 0;
IF COL_LENGTH(N'dbo.ingestion_run', N'source_columns_json') IS NULL
    ALTER TABLE dbo.ingestion_run ADD source_columns_json NVARCHAR(MAX) NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.ingestion_run') AND name=N'idx_ingestion_source_sha256')
    CREATE INDEX idx_ingestion_source_sha256 ON dbo.ingestion_run(source_sha256, status) WHERE source_sha256 IS NOT NULL;
GO

IF OBJECT_ID(N'dbo.system_state', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.system_state (
        state_key NVARCHAR(100) NOT NULL CONSTRAINT pk_system_state PRIMARY KEY,
        int_value BIGINT NULL,
        text_value NVARCHAR(MAX) NULL,
        updated_at DATETIME2(0) NOT NULL CONSTRAINT df_system_state_updated DEFAULT SYSUTCDATETIME()
    );
END;
IF NOT EXISTS (SELECT 1 FROM dbo.system_state WHERE state_key=N'data_version')
    INSERT INTO dbo.system_state(state_key,int_value) VALUES (N'data_version', 1);
GO

IF OBJECT_ID(N'dbo.data_quality_issue', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.data_quality_issue (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT pk_data_quality_issue PRIMARY KEY,
        ingestion_run_id BIGINT NOT NULL,
        dimension_name NVARCHAR(30) NOT NULL,
        field_name NVARCHAR(100) NULL,
        issue_code NVARCHAR(80) NOT NULL,
        issue_count BIGINT NOT NULL,
        sample_json NVARCHAR(MAX) NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT df_quality_issue_created DEFAULT SYSUTCDATETIME(),
        CONSTRAINT fk_quality_issue_ingestion FOREIGN KEY (ingestion_run_id) REFERENCES dbo.ingestion_run(id)
    );
    CREATE INDEX idx_quality_issue_run ON dbo.data_quality_issue(ingestion_run_id, dimension_name);
END;
GO

IF OBJECT_ID(N'dbo.backup_job', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.backup_job (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT pk_backup_job PRIMARY KEY,
        backup_path NVARCHAR(1000) NOT NULL,
        backup_type NVARCHAR(20) NOT NULL CONSTRAINT df_backup_type DEFAULT 'full',
        status NVARCHAR(20) NOT NULL,
        size_bytes BIGINT NULL,
        checksum_verified BIT NOT NULL CONSTRAINT df_backup_verified DEFAULT 0,
        started_at DATETIME2(0) NOT NULL CONSTRAINT df_backup_started DEFAULT SYSUTCDATETIME(),
        finished_at DATETIME2(0) NULL,
        error_message NVARCHAR(2000) NULL
    );
    CREATE INDEX idx_backup_job_started ON dbo.backup_job(started_at DESC);
END;
GO

IF OBJECT_ID(N'dbo.disease_procedure_stat', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.disease_procedure_stat (
        discharge_year SMALLINT NOT NULL,
        diagnosis_code NVARCHAR(20) NOT NULL,
        diagnosis_description NVARCHAR(300) NULL,
        procedure_code NVARCHAR(20) NOT NULL,
        procedure_description NVARCHAR(300) NULL,
        pair_count BIGINT NOT NULL,
        updated_at DATETIME2(0) NOT NULL CONSTRAINT df_dp_stat_updated DEFAULT SYSUTCDATETIME(),
        CONSTRAINT pk_disease_procedure_stat PRIMARY KEY
            (discharge_year, diagnosis_code, procedure_code),
        CONSTRAINT ck_dp_stat_pair_count CHECK (pair_count > 0)
    );
    CREATE INDEX idx_dp_stat_diagnosis
        ON dbo.disease_procedure_stat(discharge_year, diagnosis_code) INCLUDE(pair_count);
    CREATE INDEX idx_dp_stat_procedure
        ON dbo.disease_procedure_stat(discharge_year, procedure_code) INCLUDE(pair_count);
END;
GO

IF OBJECT_ID(N'dbo.ml_model', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ml_model (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT pk_ml_model PRIMARY KEY,
        model_name NVARCHAR(100) NOT NULL,
        model_version NVARCHAR(100) NOT NULL CONSTRAINT uq_ml_model_version UNIQUE,
        artifact_path NVARCHAR(1000) NOT NULL,
        algorithm NVARCHAR(100) NOT NULL,
        training_data_version BIGINT NOT NULL,
        train_rows INT NOT NULL,
        test_rows INT NOT NULL,
        holdout_year SMALLINT NULL,
        metrics_json NVARCHAR(MAX) NOT NULL,
        feature_schema_json NVARCHAR(MAX) NOT NULL,
        status NVARCHAR(20) NOT NULL CONSTRAINT ck_ml_model_status
            CHECK (status IN ('candidate','active','archived','failed')),
        trained_at DATETIME2(0) NOT NULL CONSTRAINT df_ml_model_trained DEFAULT SYSUTCDATETIME(),
        activated_at DATETIME2(0) NULL
    );
    CREATE INDEX idx_ml_model_active ON dbo.ml_model(model_name,status,trained_at DESC);
END;
GO

IF OBJECT_ID(N'dbo.analytics_summary_stat', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.analytics_summary_stat (
        scope_service_area NVARCHAR(100) NOT NULL CONSTRAINT pk_analytics_summary_stat PRIMARY KEY,
        discharges BIGINT NOT NULL,
        length_of_stay_sum BIGINT NOT NULL,
        length_of_stay_count BIGINT NOT NULL,
        total_charges_sum DECIMAL(38,2) NOT NULL,
        total_charges_count BIGINT NOT NULL,
        updated_at DATETIME2(0) NOT NULL CONSTRAINT df_analytics_summary_updated DEFAULT SYSUTCDATETIME()
    );
END;
GO

IF OBJECT_ID(N'dbo.analytics_dimension_stat', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.analytics_dimension_stat (
        scope_service_area NVARCHAR(100) NOT NULL,
        dimension_name NVARCHAR(30) NOT NULL,
        dimension_value NVARCHAR(300) NOT NULL,
        record_count BIGINT NOT NULL,
        length_of_stay_sum BIGINT NOT NULL,
        length_of_stay_count BIGINT NOT NULL,
        total_charges_sum DECIMAL(38,2) NOT NULL,
        total_charges_count BIGINT NOT NULL,
        total_costs_sum DECIMAL(38,2) NOT NULL,
        total_costs_count BIGINT NOT NULL,
        updated_at DATETIME2(0) NOT NULL CONSTRAINT df_analytics_dimension_updated DEFAULT SYSUTCDATETIME(),
        CONSTRAINT pk_analytics_dimension_stat PRIMARY KEY(scope_service_area,dimension_name,dimension_value)
    );
    CREATE INDEX idx_analytics_dimension_rank
        ON dbo.analytics_dimension_stat(scope_service_area,dimension_name,record_count DESC);
END;
GO

IF OBJECT_ID(N'dbo.analytics_facility_stat', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.analytics_facility_stat (
        scope_service_area NVARCHAR(100) NOT NULL,
        facility_name NVARCHAR(200) NOT NULL,
        CONSTRAINT pk_analytics_facility_stat PRIMARY KEY(scope_service_area,facility_name)
    );
END;
GO

IF OBJECT_ID(N'dbo.users', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.users (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT pk_users PRIMARY KEY,
        username NVARCHAR(50) NOT NULL,
        username_normalized NVARCHAR(50) NOT NULL CONSTRAINT uq_users_username_normalized UNIQUE,
        password_hash NVARCHAR(255) NOT NULL,
        display_name NVARCHAR(100) NULL,
        role NVARCHAR(20) NOT NULL CONSTRAINT ck_users_role CHECK (role IN ('patient', 'doctor', 'admin')),
        email NVARCHAR(200) NULL,
        is_active BIT NOT NULL CONSTRAINT df_users_active DEFAULT 1,
        failed_login_attempts TINYINT NOT NULL CONSTRAINT df_users_failed_attempts DEFAULT 0,
        locked_until DATETIME2(0) NULL,
        must_change_password BIT NOT NULL CONSTRAINT df_users_change_password DEFAULT 1,
        password_changed_at DATETIME2(0) NULL,
        last_login_at DATETIME2(0) NULL,
        created_by BIGINT NULL,
        deleted_at DATETIME2(0) NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT df_users_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2(0) NOT NULL CONSTRAINT df_users_updated_at DEFAULT SYSUTCDATETIME(),
        row_version ROWVERSION NOT NULL,
        CONSTRAINT fk_users_created_by FOREIGN KEY (created_by) REFERENCES dbo.users(id)
    );
END;
GO

IF OBJECT_ID(N'dbo.security_audit', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.security_audit (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT pk_security_audit PRIMARY KEY,
        user_id BIGINT NULL,
        username NVARCHAR(50) NULL,
        action NVARCHAR(80) NOT NULL,
        detail NVARCHAR(1000) NULL,
        ip_address NVARCHAR(64) NULL,
        user_agent NVARCHAR(500) NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT df_security_audit_created_at DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX idx_security_audit_created_at ON dbo.security_audit(created_at DESC);
    CREATE INDEX idx_security_audit_user_id ON dbo.security_audit(user_id);
END;
GO

IF OBJECT_ID(N'dbo.analysis_report', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.analysis_report (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT pk_analysis_report PRIMARY KEY,
        title NVARCHAR(100) NOT NULL,
        content NVARCHAR(MAX) NOT NULL,
        status NVARCHAR(20) NOT NULL CONSTRAINT df_report_status DEFAULT 'draft'
            CONSTRAINT ck_report_status CHECK (status IN ('draft', 'published', 'archived')),
        created_by BIGINT NOT NULL,
        published_at DATETIME2(0) NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT df_report_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2(0) NOT NULL CONSTRAINT df_report_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT fk_report_created_by FOREIGN KEY (created_by) REFERENCES dbo.users(id)
    );
END;
GO

IF OBJECT_ID(N'dbo.ai_conversation', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ai_conversation (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT pk_ai_conversation PRIMARY KEY,
        public_id CHAR(36) NOT NULL CONSTRAINT uq_ai_conversation_public UNIQUE,
        user_id BIGINT NOT NULL,
        title NVARCHAR(100) NOT NULL,
        last_intent_json NVARCHAR(MAX) NULL,
        state_json NVARCHAR(MAX) NULL,
        status NVARCHAR(20) NOT NULL CONSTRAINT df_ai_conversation_status DEFAULT 'active'
            CONSTRAINT ck_ai_conversation_status CHECK (status IN ('active','archived')),
        created_at DATETIME2(0) NOT NULL CONSTRAINT df_ai_conversation_created DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2(0) NOT NULL CONSTRAINT df_ai_conversation_updated DEFAULT SYSUTCDATETIME(),
        CONSTRAINT fk_ai_conversation_user FOREIGN KEY(user_id) REFERENCES dbo.users(id)
    );
    CREATE INDEX idx_ai_conversation_user ON dbo.ai_conversation(user_id,status,updated_at DESC);
END;
GO

IF OBJECT_ID(N'dbo.ai_conversation_message', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ai_conversation_message (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT pk_ai_conversation_message PRIMARY KEY,
        conversation_id BIGINT NOT NULL,
        role NVARCHAR(20) NOT NULL CONSTRAINT ck_ai_message_role CHECK (role IN ('user','assistant')),
        content NVARCHAR(MAX) NOT NULL,
        request_id NVARCHAR(64) NULL,
        payload_json NVARCHAR(MAX) NULL,
        created_at DATETIME2(0) NOT NULL CONSTRAINT df_ai_message_created DEFAULT SYSUTCDATETIME(),
        CONSTRAINT fk_ai_message_conversation FOREIGN KEY(conversation_id)
            REFERENCES dbo.ai_conversation(id)
    );
    CREATE INDEX idx_ai_message_conversation ON dbo.ai_conversation_message(conversation_id,id);
END;
GO
