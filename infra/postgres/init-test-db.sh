#!/bin/sh
# Runs once, when the database volume is first created (docker-entrypoint-initdb.d).
# Creates <db>_test beside the service's own database, for that service's local pytest run.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE DATABASE "${POSTGRES_DB}_test" OWNER "$POSTGRES_USER";
SQL
