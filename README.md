# Share Bear

A modern, sustainable marketplace built for the Baylor community.

## Project Structure

- `config/`: Django project configuration (`settings.py`, `urls.py`, ASGI/WSGI).
- `core/`: Current homepage/view logic.
- `users/`: Custom authentication app with the project's `User` model.
- `templates/`: Global templates (currently includes `index.html`).
- `manage.py`: Django management entry point.

## Technical Stack

- **Framework:** Django 6.0.3
- **Database:** SQLite by default, Supabase Postgres via `DATABASE_URL`
- **Auth Model:** Custom user model via `AUTH_USER_MODEL = 'users.User'`
- **Environment Management:** Root `.env` file loaded by `config/settings.py`

## User Model Foundation

The project uses a dedicated `users` app with `users.User` inheriting Django `AbstractUser`.

- Uses Django-native authorization semantics:
  - Regular user: `is_staff=False`, `is_superuser=False`
  - Staff/admin operator: `is_staff=True`, `is_superuser=False`
  - Superuser: `is_superuser=True`
- Includes optional `graduation_year` to support future student workflows.
- Custom user model is registered in Django admin.

## Getting Started

### Prerequisites

- Python 3.10+
- `pip`

### Installation

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd share-bear
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Create `.env` in the project root:

   ```env
   DEBUG=True
   SECRET_KEY=your-development-secret-key
   ALLOWED_HOSTS=baylorshare.com,www.baylorshare.com,localhost,127.0.0.1
   # Optional: Supabase/Postgres connection string (when set, overrides SQLite)
   DATABASE_URL=postgresql://postgres.iaehsjgixiomahxscdbj:[YOUR-PASSWORD]@aws-1-us-east-2.pooler.supabase.com:5432/postgres?sslmode=require
   ```

5. Apply migrations:

   ```bash
   python3 manage.py migrate
   ```

6. Run the development server:

   ```bash
   python3 manage.py runserver
   ```

## Common Commands

```bash
# Project checks
python3 manage.py check

# Run all tests
python3 manage.py test

# Run users app tests only
python3 manage.py test users.tests

# Create admin/superuser account
python3 manage.py createsuperuser
```

## Supabase Database Setup

When `DATABASE_URL` is set, Django uses Postgres (`django.db.backends.postgresql`).
When `DATABASE_URL` is not set, Django falls back to local SQLite.

1. Add the Supabase connection string in `.env`:

   ```env
   DATABASE_URL=postgresql://postgres.iaehsjgixiomahxscdbj:[YOUR-PASSWORD]@aws-1-us-east-2.pooler.supabase.com:5432/postgres?sslmode=require
   ```

2. Install dependencies (includes PostgreSQL driver):

   ```bash
   pip install -r requirements.txt
   ```

3. Run migrations against Supabase:

   ```bash
   python3 manage.py migrate
   ```

4. Optional: if you change models first, generate + apply migrations:

   ```bash
   python3 manage.py makemigrations
   python3 manage.py migrate
   ```

## Vercel Deployment Notes

- This is a Django app deployed on Vercel using `vercel.json` and `@vercel/python`.
- Vercel Analytics for Django is supported by loading:

  ```html
  <script defer src="/_vercel/insights/script.js"></script>
  ```

- Analytics loading is controlled by:

  ```env
  VERCEL_ANALYTICS_ENABLED=True
  ```

- Keep `ALLOWED_HOSTS` set to include your Vercel domain(s).
- Production host defaults in settings include:
  - `baylorshare.com`
  - `www.baylorshare.com`
- By default, tests use in-memory SQLite even when `DATABASE_URL` points to Supabase (avoids pooled Postgres test DB teardown errors). To force Postgres tests, set:

  ```env
  USE_POSTGRES_FOR_TESTS=True
  ```

## Production Considerations

- Set `DEBUG=False` and provide a secure `SECRET_KEY`.
- Set explicit `ALLOWED_HOSTS`.
- Run `python3 manage.py collectstatic` and serve static assets via your deployment stack.
- Move to PostgreSQL (or Supabase Postgres) for production-scale usage.
