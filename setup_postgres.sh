#!/bin/bash
set -e

# Update system
sudo apt update

# Install PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# Start PostgreSQL service
sudo service postgresql start

# Setup DB and user
sudo -u postgres psql <<EOF
DO
\$do\$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_catalog.pg_database WHERE datname = 'smart_scheduler'
   ) THEN
      CREATE DATABASE smart_scheduler;
   END IF;
END
\$do\$;

DO
\$do\$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_catalog.pg_roles WHERE rolname = 'smart_user'
   ) THEN
      CREATE USER smart_user WITH PASSWORD 'smart_password';
   END IF;
END
\$do\$;

GRANT ALL PRIVILEGES ON DATABASE smart_scheduler TO smart_user;
EOF
