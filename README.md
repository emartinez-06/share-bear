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
- **Database (current):** SQLite (`db.sqlite3`)
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
   ALLOWED_HOSTS=localhost,127.0.0.1
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

## Production Considerations

- Set `DEBUG=False` and provide a secure `SECRET_KEY`.
- Set explicit `ALLOWED_HOSTS`.
- Run `python3 manage.py collectstatic` and serve static assets via your deployment stack.
- Move to PostgreSQL (or Supabase Postgres) for production-scale usage.
