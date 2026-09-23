FROM mirror.gcr.io/library/debian:trixie-slim AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

LABEL org.opencontainers.image.source="https://github.com/Ascendor/mutual-games-finder-for-lanparties"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app
ENV PYTHONPATH=/app \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

FROM base AS tooling
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PYTHON_BIN_DIR=/usr/local/bin \
    UV_PYTHON_PREFERENCE=only-managed \
    UV_LINK_MODE=copy
COPY backend/.python-version ./
RUN uv python install
ENV UV_PYTHON_DOWNLOADS=never

FROM tooling AS production-dependencies
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups

FROM production-dependencies AS test-dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --group test

FROM base AS application
COPY --from=tooling /opt/python /opt/python
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./

COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY LICENSE THIRD_PARTY_NOTICES.md /licenses/
COPY LICENSES /licenses/

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

FROM application AS test
COPY --from=test-dependencies /app/.venv /app/.venv
COPY backend/tests ./tests
CMD ["pytest"]

FROM application AS production
COPY --from=production-dependencies /app/.venv /app/.venv
