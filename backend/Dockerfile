FROM mirror.gcr.io/library/python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/Ascendor/mutual-games-finder-for-lanparties"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app
ENV PYTHONPATH=/app

COPY backend/requirements.lock ./requirements.lock
COPY backend/pyproject.toml ./pyproject.toml
COPY backend/check_dependencies.py ./check_dependencies.py
RUN pip install --no-cache-dir --requirement requirements.lock \
    && python check_dependencies.py \
    && pip check

COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY backend/tests ./tests
COPY LICENSE THIRD_PARTY_NOTICES.md /licenses/
COPY LICENSES /licenses/

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
