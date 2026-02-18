-- Minimal bootstrap для webhook_service
-- Создание БД, пользователя и прав

CREATE DATABASE biretos_automation;
CREATE USER biretos_user WITH PASSWORD 'biretos_pass';
GRANT ALL PRIVILEGES ON DATABASE biretos_automation TO biretos_user;





















