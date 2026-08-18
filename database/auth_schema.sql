USE pa_system;

CREATE TABLE IF NOT EXISTS users (
    user_id       VARCHAR(64) PRIMARY KEY,
    email         VARCHAR(128) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          ENUM('initiator', 'insurer') NOT NULL,
    full_name     VARCHAR(128),
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

ALTER TABLE pa_request
    ADD COLUMN urgency VARCHAR(16) DEFAULT 'LOW',
    ADD COLUMN parent_request_id VARCHAR(64) NULL,
    ADD COLUMN insurer_confirmed_by VARCHAR(64) NULL,
    ADD COLUMN insurer_confirmed_at DATETIME NULL,
    ADD COLUMN insurer_final_status VARCHAR(32) NULL,
    ADD COLUMN insurer_override_note TEXT NULL,
    ADD FOREIGN KEY (parent_request_id) REFERENCES pa_request(request_id);

CREATE TABLE IF NOT EXISTS rate_limit_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    identifier   VARCHAR(128) NOT NULL,
    endpoint     VARCHAR(128) NOT NULL,
    requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_rate_check (identifier, endpoint, requested_at)
) ENGINE=InnoDB;
