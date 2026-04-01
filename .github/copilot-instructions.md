# Copilot Instructions for `share-bear`

## Build, test, and lint commands

Use Python 3 with the project virtual environment activated.

```bash
pip install -r requirements.txt
python3 manage.py migrate
python3 manage.py runserver
```

Validation and test commands used in this repo:

```bash
# Django project/system validation (closest equivalent to linting in this repo)
python3 manage.py check

# Full test suite
python3 manage.py test

# Single test module
python3 manage.py test core.tests

# Single test case class
python3 manage.py test core.tests.YourTestClass

# Single test method
python3 manage.py test core.tests.YourTestClass.test_specific_behavior
```

## High-level architecture

- This is a minimal Django 6 project with one app: `core`.
- `config/settings.py` configures the project and manually loads environment variables from a root `.env` file before settings are resolved.
- `config/urls.py` is the main URL router. The root path (`""`) maps directly to `core.views.home_view`.
- `core/views.py` currently provides `home_view`, which renders `templates/index.html`.
- Template loading is configured globally through `TEMPLATES[0]["DIRS"] = [BASE_DIR / "templates"]`, with `APP_DIRS=True` for app-local templates.
- Default persistence is SQLite at `db.sqlite3` (`DATABASES["default"]` in `config/settings.py`).

## Key repository conventions

- Environment configuration is expected via `.env` with plain `KEY=VALUE` lines; settings read from `os.environ` (`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`).
- `SECRET_KEY` is not hardcoded; local/dev setup should provide it in `.env`.
- `ALLOWED_HOSTS` is configured as a comma-separated environment variable and split into a Python list in settings.
- Root-page behavior is centralized through `config/urls.py` -> `core.views.home_view` -> `templates/index.html`; preserve this flow when changing the homepage path/rendering behavior.
- Dependencies are pinned in `requirements.txt`; update pins intentionally when changing Django or runtime libraries.
