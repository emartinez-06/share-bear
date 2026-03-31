# Share Bear

A streamlined Django 6.0 project

## Project Structure

- `config/`: Core project configuration (settings, URLs, ASGI/WSGI).
- `core/`: Primary application logic, models, and migrations.
- `templates/`: Global UI components and page layouts.
- `manage.py`: Administrative entry point.

## Technical Stack

- **Framework:** Django 6.0.3
- **Database:** SQLite (Default, configurable via `DATABASES` in `settings.py`)
- **Environment Management:** Native `.env` support for configuration.

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

2. Initialize virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Configuration:
   Create a `.env` file in the root directory:

   ```env
   DEBUG=True
   SECRET_KEY=your-development-secret-key
   ALLOWED_HOSTS=localhost,127.0.0.1
   ```

5. Database setup:

   ```bash
   python manage.py migrate
   ```

6. Run development server:
   ```bash
   python manage.py runserver
   ```

## Production Considerations

- **Environment Variables:** Ensure `DEBUG` is set to `False` and a secure `SECRET_KEY` is provided in production.
- **Allowed Hosts:** Explicitly define `ALLOWED_HOSTS` to prevent HTTP Host header attacks.
- **Static Files:** Configure a production-grade static file server or CDN and run `python manage.py collectstatic`.
- **Database:** Transition to a robust database system like PostgreSQL for multi-user production environments.
- **WSGI/ASGI:** Use `gunicorn` or `uvicorn` behind a reverse proxy like Nginx.
