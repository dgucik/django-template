# Django Modular Monolith Template

A Django backend template for building a loosely coupled modular monolith with
lightweight CQRS and aggregate-based domain models.

See [AGENTS.md](AGENTS.md) for architecture and contribution rules.

## Stack

- Python 3.13
- Django 6 and Django REST Framework
- `uv` for Python and dependency management
- Ruff, mypy, django-stubs, and Import Linter
- SQLite by default

## Setup

Install [`uv`](https://docs.astral.sh/uv/), then run:

```bash
git clone <repository-url>
cd django-template/backend

cp .env.example .env
uv sync --locked --group dev
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

- API: `http://127.0.0.1:8000/api/`
- Admin: `http://127.0.0.1:8000/admin/`

Using `uv run` does not require activating `.venv`. If another project's virtual
environment is active, run `deactivate` first.

## Configuration

Local settings are loaded from `backend/.env`. Available variables are documented
in `backend/.env.example`. SQLite is used unless `DJANGO_DB_*` variables configure
another database. Never commit `.env` or real secrets.

## Project structure

```text
.
├── AGENTS.md
├── README.md
├── backend/
│   ├── apps/             # business modules
│   ├── config/           # Django configuration
│   ├── core/             # shared technical code
│   ├── manage.py
│   ├── pyproject.toml
│   └── uv.lock
└── .github/              # CI configuration
```

A business module should follow this structure:

```text
apps/orders/
├── commands/
│   └── order_create_command.py  # command + handler
├── queries/
│   └── order_get_query.py       # query + handler + view model
├── models/
│   └── order_model.py
├── services/             # optional domain services
├── factories/            # optional aggregate factories
├── selectors.py          # thin Django ORM read helpers
├── migrations/
├── admin.py
├── apps.py
├── urls.py
└── views.py
```

Create optional directories only when needed.

Use `selectors.py` by default. Convert it to a `selectors/` package only when the
file becomes too large to maintain clearly.

## Architecture

Each Django app is an independent business module. Its only public interfaces
are `commands` and `queries`. Models, selectors, services, and factories are private.
Cross-module imports must target these package interfaces, for example
`from apps.orders.commands import OrderCreateCommand`, never their internal files.

- Commands mutate state, run inside `transaction.atomic`, and return `None`.
- Queries never write to the database and return dedicated view models.
- Business types follow `Entity + Action + Layer`, for example
  `OrderCreateCommand`; models follow `Entity + Layer`, for example `OrderModel`.
- Commands and queries in the same module do not depend on each other.
- Cross-module dependencies must remain acyclic.
- An aggregate root owns its child entities and enforces their invariants.
- Child entities must not be modified directly outside the aggregate.

## Development commands

Run from `backend/`:

```bash
uv run python manage.py runserver
uv run python manage.py test

uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run lint-imports

uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
```

Enable pre-commit from the repository root:

```bash
uv --directory backend run pre-commit install
uv --directory backend run pre-commit run --all-files
```
