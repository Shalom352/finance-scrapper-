# ============================================================
# UMOA Banking Intelligence — Backend (FastAPI) image
#
# - Python 3.11 (same as the development virtualenv), pinned requirements
# - runs as an unprivileged user
# - applies the Alembic migrations, then starts uvicorn
# No secret is baked into the image: configuration comes from the environment.
# ============================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
    && mkdir -p /app/data/downloads && chown -R app:app /app/data

COPY --chown=app:app alembic.ini ./
COPY --chown=app:app app ./app
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app scraping ./scraping

USER app
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"

# Migrations are idempotent (alembic upgrade head); the server only starts if they succeed.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --no-server-header --no-access-log"]
