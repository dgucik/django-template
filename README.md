# Django backend

## Development

Requirements: Python 3.13 and [`uv`](https://docs.astral.sh/uv/).

Development uses SQLite:

```bash
cd backend
cp .env.example .env
uv sync --locked --group dev
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

- API: `http://127.0.0.1:8000/api/`
- Admin: `http://127.0.0.1:8000/admin/`

After changing models:

```bash
uv run python manage.py makemigrations
uv run python manage.py migrate
```

## New module

From the repository root:

```bash
./scripts/create_app.sh orders
```

Then add `"apps.orders"` to `INSTALLED_APPS` and include
`apps.orders.urls` in the API URL configuration when the module exposes
endpoints.

Import Linter automatically checks every `apps.*` module for cycles and internal
layer direction. Before importing between business modules, explicitly decide
their dependency level: which modules may import the new module and which
modules it may import. Encode that decision as an additional Import Linter
contract in `backend/pyproject.toml`; do not rely only on documentation or an
informal convention.

For example, a layers contract ordered from highest to lowest:

```toml
[[tool.importlinter.contracts]]
name = "Business module dependency levels"
type = "layers"
layers = [
    "apps.checkout",
    "apps.orders",
    "apps.users",
]
```

Here `checkout` may import `orders` and `users`, while `users` cannot import
either module.

## Docker

Docker Compose runs the production backend with Gunicorn and PostgreSQL.
PostgreSQL roles and Django migrations are initialized automatically.

From the repository root:

```bash
cp backend/.env.example .env
```

Change all passwords and `DJANGO_SECRET_KEY` in `.env`, then run:

```bash
docker compose up --build --detach
docker compose logs --follow backend
```

Stop containers:

```bash
docker compose down
```

Delete containers and the local PostgreSQL data:

```bash
docker compose down --volumes
```

## Checks

Run from `backend/`:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run lint-imports
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest
../scripts/ci/backend/mutation-test.sh
```

`mutmut` runs mutation testing against function and method bodies in
`backend/apps/`. Tests colocated with business modules under `apps/` are
executed but are not mutated. Architecture tests remain in the separate Import
Linter and pytest checks because they inspect uninstrumented source code. The
mutation check passes when every generated mutant is killed; it also handles a
new project that does not contain any production functions yet. Inspect
surviving or otherwise non-killed mutants with:

```bash
uv run mutmut run
uv run mutmut results
uv run mutmut browse
```

Mutation testing requires a system with `fork` support. On Windows, run it
inside WSL.
