FROM mirror.gcr.io/library/python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY tests ./tests

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]



