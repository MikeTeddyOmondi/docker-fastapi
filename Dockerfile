# uv-based image: ships uv + Python, no separate pip step.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Resolve and install dependencies first for better layer caching.
# `uv sync` creates uv.lock if it is missing; commit the lock for fully
# reproducible builds and switch this to `uv sync --frozen --no-dev`.
COPY pyproject.toml ./
RUN uv sync --no-dev

COPY app ./app

EXPOSE 80

# docker-py is blocking; uvicorn runs the sync routes in a threadpool.
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
