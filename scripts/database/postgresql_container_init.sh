#!/bin/sh
set -eu

psql \
    --set ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --variable writer_user="$DJANGO_DB_USER" \
    --variable writer_password="$DJANGO_DB_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN', :'writer_user')
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'writer_user'
)
\gexec

SELECT format(
    'ALTER ROLE %I WITH PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE '
    'NOINHERIT NOREPLICATION NOBYPASSRLS',
    :'writer_user',
    :'writer_password'
)
\gexec

SELECT format(
    'ALTER DATABASE %I OWNER TO %I',
    current_database(),
    :'writer_user'
)
\gexec
SQL

psql \
    --set ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --variable readonly_user="$DJANGO_DB_READONLY_USER" \
    --variable readonly_password="$DJANGO_DB_READONLY_PASSWORD" \
    --variable owner_user="$DJANGO_DB_USER" \
    --file /opt/database/postgresql_readonly_role.sql
