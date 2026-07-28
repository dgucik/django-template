#!/bin/sh
set -eu

if [ "$DJANGO_DB_USER" = "$POSTGRES_USER" ] \
    || [ "$DJANGO_DB_READONLY_USER" = "$POSTGRES_USER" ] \
    || [ "$DJANGO_DB_USER" = "$DJANGO_DB_READONLY_USER" ]; then
    echo "PostgreSQL administrator, writer, and read-only roles must be distinct" >&2
    exit 1
fi

psql \
    --set ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --variable writer_user="$DJANGO_DB_USER" \
    --variable writer_password="$DJANGO_DB_PASSWORD" \
    --variable readonly_user="$DJANGO_DB_READONLY_USER" \
    --variable readonly_password="$DJANGO_DB_READONLY_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'writer_user', :'writer_password')
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = :'writer_user'
)
\gexec

SELECT format('ALTER DATABASE %I OWNER TO %I', current_database(), :'writer_user')
\gexec

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'readonly_user', :'readonly_password')
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = :'readonly_user'
)
\gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'readonly_user')
\gexec

SELECT format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC', current_database())
\gexec

GRANT USAGE ON SCHEMA public TO :"readonly_user";
GRANT SELECT ON ALL TABLES IN SCHEMA public TO :"readonly_user";
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM :"readonly_user";
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM :"readonly_user";

ALTER DEFAULT PRIVILEGES FOR ROLE :"writer_user" IN SCHEMA public
GRANT SELECT ON TABLES TO :"readonly_user";

REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE :"writer_user"
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
SQL
