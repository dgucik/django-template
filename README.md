# Django backend

## Development

Requirements: Python 3.13 and [`uv`](https://docs.astral.sh/uv/).

Development uses SQLite:

```bash
cd backend
cp .env.local.example .env
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
cp .env.docker.example .env
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

Quality gates, test ownership, and configuration changes are documented in
[CODE_QUALITY.md](CODE_QUALITY.md).

The command/query interface strategy for scaling, microservice extraction, and
Django forms/templates is documented in
[ARCHITECTURE_SCALING.md](ARCHITECTURE_SCALING.md).
