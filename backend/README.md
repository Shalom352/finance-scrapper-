# UMOA Banking Intelligence — Backend

## Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI (async)
- **ORM**: SQLAlchemy 2.0 (async)
- **Validation**: Pydantic v2
- **Migrations**: Alembic
- **Database**: PostgreSQL 16 (via asyncpg)
- **Logging**: structlog
- **Tests**: pytest + pytest-asyncio

## Development setup

```bash
# Create virtual environment
py -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Install dev dependencies
pip install -r requirements-dev.txt

# Copy environment file
cp ../.env.example ../.env
# Edit .env with your values

# Start PostgreSQL (from project root)
docker-compose up -d postgres

# Run migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

## Health checks

- `GET /health` — Application liveness (no DB required)
- `GET /api/v1/health` — Full health including database

## Running tests

```bash
# Activate venv first
.venv\Scripts\activate

# Run all tests
pytest

# With coverage
pytest --cov=app --cov-report=term-missing

# Specific test file
pytest tests/test_health.py -v
```

## Database migrations

```bash
# Create a new migration (after modifying models)
alembic revision --autogenerate -m "description of change"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1

# View migration history
alembic history
```

## Code quality

```bash
# Linting
ruff check .

# Formatting
black .

# Type checking
mypy app/
```

## Environment variables

See `../.env.example` for all available variables.
Never commit `.env` to version control.

## Architecture

```
app/
├── main.py          # FastAPI app factory
├── core/
│   ├── config.py    # pydantic-settings configuration
│   └── logging.py   # structlog setup
├── db/
│   ├── base.py      # SQLAlchemy declarative base
│   ├── engine.py    # Async engine
│   └── session.py   # Session factory + DI
├── api/
│   └── v1/
│       └── health.py  # Health endpoints
├── models/          # SQLAlchemy models (Phase 1+)
├── schemas/         # Pydantic schemas (Phase 1+)
└── services/        # Business logic (Phase 1+)
```

## Data integrity rules

See `../docs/dev-rules.md` for the full rules.

In summary:
- **Never invent financial data**
- Every financial value must have: source, document, page, period, original value, unit, extraction method, validation status
- Use `needs_review` status for uncertain extractions
- A value can only be `verified` if `verified_at` and `verified_by` are set
