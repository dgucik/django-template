\set ON_ERROR_STOP on

\if :{?readonly_user}
\else
\echo 'readonly_user is required'
\quit 1
\endif

\if :{?readonly_password}
\else
\echo 'readonly_password is required'
\quit 1
\endif

\if :{?owner_user}
\else
\echo 'owner_user is required'
\quit 1
\endif

SELECT format('CREATE ROLE %I LOGIN', :'readonly_user')
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'readonly_user'
)
\gexec

SELECT format(
    'ALTER ROLE %I WITH PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE '
    'NOINHERIT NOREPLICATION NOBYPASSRLS',
    :'readonly_user',
    :'readonly_password'
)
\gexec

SELECT NOT EXISTS (
    SELECT 1
    FROM pg_auth_members
    JOIN pg_roles ON pg_roles.oid = pg_auth_members.member
    WHERE pg_roles.rolname = :'readonly_user'
) AS readonly_role_is_isolated
\gset

\if :readonly_role_is_isolated
\else
\echo 'readonly_user must not be a member of another PostgreSQL role'
\quit 1
\endif

SELECT format(
    'GRANT CONNECT ON DATABASE %I TO %I',
    current_database(),
    :'readonly_user'
)
\gexec

SELECT format(
    'REVOKE TEMPORARY ON DATABASE %I FROM %I',
    current_database(),
    :'readonly_user'
)
\gexec

GRANT USAGE ON SCHEMA public TO :"readonly_user";
REVOKE CREATE ON SCHEMA public FROM :"readonly_user";

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM :"readonly_user";
GRANT SELECT ON ALL TABLES IN SCHEMA public TO :"readonly_user";
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM :"readonly_user";
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM :"readonly_user";

ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_user" IN SCHEMA public
GRANT SELECT ON TABLES TO :"readonly_user";

REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_user"
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
