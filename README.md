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
```
