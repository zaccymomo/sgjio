-- Runs once when the docker compose database is first created.
-- The test suite uses its own database so it never touches your dev data.
CREATE DATABASE sgjio_test OWNER sgjio;
