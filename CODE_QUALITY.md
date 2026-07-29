# Code quality

## Local checks

Run these checks from `backend/`; they require no Docker or other external
service:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run lint-imports
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest
```

PostgreSQL permission tests and mutation testing are CI gates. Run them locally
only when the required environment is available: PostgreSQL tests need Docker
Compose, while `../scripts/ci/backend/mutation-test.sh` needs `fork` support.

## Gates

| Gate | Scope and configuration |
| --- | --- |
| Ruff | Enforces style, import order, upgrades, bug-risk, Django, docstring, and complexity rules. `C90` limits production complexity to 10; test-only `C901` is exempt because architecture inspectors walk ASTs. Configure rules, limits, and narrow ignores in `backend/pyproject.toml`. |
| Ruff format | Checks formatting. Apply it with `uv run ruff format .`. |
| mypy | Strict typing with Django stubs. Use complete annotations and fix types rather than adding broad ignores; configure it in `backend/pyproject.toml`. |
| Import Linter | Verifies app acyclicity and presentation-to-domain layer direction. Contracts live in `backend/pyproject.toml`; add an explicit contract before a new cross-module dependency. |
| Django checks | `manage.py check` validates Django configuration; `makemigrations --check --dry-run` detects missing migrations. Create migrations for model changes; never edit applied migrations. |
| pytest | Runs unit, integration, and architecture tests. The local default excludes `postgresql`; CI runs that suite with PostgreSQL and dedicated database roles. |
| mutmut | CI mutates function and method bodies under `apps/`; colocated app tests run but are not mutated. The script skips cleanly when no production functions exist. Inspect survivors with `uv run mutmut run`, `results`, and `browse`; it requires `fork` support (use WSL on Windows). |

## CI

GitHub Actions workflow [backend-ci.yml](.github/workflows/backend-ci.yml) runs
on pull requests and pushes to `main` or `develop` when backend, database, CI,
or Docker configuration changes. It uses locked dependencies through the shared
setup action and cancels superseded runs for the same branch.

| CI job | What it runs |
| --- | --- |
| `lint` | Ruff lint and formatting. |
| `typecheck` | Strict mypy. |
| `architecture` | Import Linter. |
| `tests` | Pytest with SQLite. |
| `mutation-tests` | The mutation-test script. |
| `postgresql-tests` | PostgreSQL 17, initialized writer/read-only roles, then pytest excluding SQLite-only tests. |
| `migrations` | Django system check and missing-migration check. |

## Test ownership

| Test location | Protects |
| --- | --- |
| `core/tests/test_app_structure.py` | App-root whitelist. Add shared elements globally; reserve `MODULE_ALLOWED_APP_ELEMENTS` for genuine one-module exceptions. |
| `core/tests/test_app_template.py` | The generator contains commands, queries, models, factories, services, views, and URLs. |
| `core/tests/test_contracts.py` | Commands, queries, and DTOs use their contract base class, frozen/slotted dataclasses, and transport-safe fields. |
| `core/tests/test_handlers.py` | Direct handler inheritance, a synchronous `handle`, atomic commands, read-only query routing, and frozen/slotted DTOs without lazy ORM values. |
| `core/tests/test_handlers_sqlite.py` | SQLite read-only connection rejects writes. |
| `core/tests/test_handlers_postgresql.py` | Dedicated read-only role, no ORM writes or temporary tables, and no ungranted security-definer functions. |
| `core/tests/test_imports.py` | Relative local imports, absolute cross-module imports, public `commands`/`queries` interfaces, and required package re-exports. |
| `core/tests/test_models.py` | Every application model inherits from `BaseModel`. |
| `core/tests/test_services_and_factories.py` | Service and factory methods are static and therefore state-free. |
| `core/tests/test_views.py` | Dataclass serializers are colocated with views; no separate serializer layer. |
| `core/tests/test_docstrings.py` | Google-style production docstrings and BDD test docstrings. |

## Change rules

- Use Python 3.13, strict typing, Google-style production docstrings, and BDD
  test docstrings with `Given`, `When`, and `Then`.
- Add tests for handlers, aggregate invariants, and fixes. New or changed
  business behavior must kill its mutants.
- Change a gate in `backend/pyproject.toml`; use per-file ignores only when the
  rule is inapplicable to that file class, not to suppress a violation.
- When adding a global app layer, update the app whitelist, the app template,
  Import Linter layers, and `AGENTS.md`. Use `MODULE_ALLOWED_APP_ELEMENTS` only
  for a real module-specific exception.
- Preserve unrelated user changes and report checks that were not run or failed.
