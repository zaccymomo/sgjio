# Built only from this directory: docker build services/notification
# Notification has no HTTP API: it is a single worker process.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/app
RUN useradd --create-home --uid 10001 app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
USER app

CMD ["sh", "-c", "alembic upgrade head && exec python -m app.worker"]
