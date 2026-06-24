default:
    just --list

# --- environment ---
install:
    uv sync

lock:
    uv lock

# --- lint & format (ruff) ---
lint:
    uv run ruff check .

fix:
    uv run ruff check --fix .

format:
    uv run ruff format .

check: lint
    uv run ruff format --check .

# --- local dev ---
run:
    uv run uvicorn app.main:app --reload --port 8448

# Publish a test deploy message onto the queue (image + name).
publish image name:
    uv run python -c "import asyncio; from app.rabbitmq import publish_deploy_message as p; asyncio.run(p('{{image}}', '{{name}}'))"

# --- docker compose (api + rabbitmq) ---
up:
    docker compose up -d --build

down:
    docker compose down

logs:
    docker compose logs -f api

ps:
    docker compose ps

# --- single-image build/run (no compose) ---
build-image:
    docker build -t ranckosolutionsinc/docker-api:v1.0 .

start-app:
    docker run -dp 8448:80 \
      -v "/var/run/docker.sock:/var/run/docker.sock" \
      -v "$(pwd)/data:/app/data" \
      --name docker-api ranckosolutionsinc/docker-api:v1.0

stop-app:
    docker stop docker-api

remove-app:
    docker rm docker-api

clean-up:
    just stop-app
    just remove-app
