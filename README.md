# Docker Control Plane API

A FastAPI service that manages Docker containers over HTTP, with an
asynchronous RabbitMQ deploy worker and a SQLite persistence/audit layer.

It models the same pattern Locci Cloud uses internally: an HTTP **control
plane** for synchronous operations, plus a **message-queue worker** for slow,
fire-and-forget deploys — with Docker as the source of truth for live state and
SQLite as the durable history.

## Architecture

```
                 ┌────────────────────────────────┐
   HTTP client ──▶  FastAPI routes (main.py)      │
                 │     │              │           │
                 │     ▼              ▼           │
                 │  docker_service   db (SQLite)  │
                 │     │   (docker-py)  ▲         │
                 └─────┼────────────────┼─────────┘
                       ▼                │
                  Docker daemon         │
                                        │
   producer ──▶ [ locci-deploy queue ]  │
                       │                │
                       ▼                │
                 rabbitmq.py consumer ──┘
                 (deploy off the event loop, persist record)
```

- **`main.py`** — HTTP routes. Plain `def` (not `async def`) because docker-py
  is blocking; FastAPI runs sync routes in a threadpool, keeping the event loop
  free for the consumer.
- **`docker_service.py`** — the only place that touches docker-py. Translates
  docker-py errors into typed domain errors and calls `reload()` after
  start/stop so returned status is never stale.
- **`db.py` / `models.py`** — SQLite via SQLModel. Stores a `Deployment` record
  per managed container so `/deployments` can report history even after a
  container is removed.
- **`rabbitmq.py`** — async consumer using aio-pika. Runs blocking Docker calls
  via `asyncio.to_thread`, acks/rejects explicitly, and degrades gracefully if
  the broker is down.

## Tooling

Dependencies and the dev environment are managed with [uv](https://docs.astral.sh/uv/);
linting and formatting use [ruff](https://docs.astral.sh/ruff/) (config in
`pyproject.toml`).

```bash
just install      # uv sync
just lint         # ruff check .
just format       # ruff format .
just check        # lint + format --check (CI-friendly)
```

## Tests

[pytest](https://docs.pytest.org/). The default suite is **hermetic** — the
Docker layer is monkeypatched and the broker is stubbed, so no daemon or
RabbitMQ is required. It exercises the parts the refactor is about: typed
error → HTTP status mapping and the SQLite audit log. A separate,
`integration`-marked test runs the real create → start → stop → delete
lifecycle against a live daemon and auto-skips when none is reachable.

```bash
just test             # hermetic unit tests (no daemon needed)
just test-integration # full lifecycle against Docker (defaults to Colima's socket)
```

The lazily-constructed Docker client honours `DOCKER_HOST`, so the integration
suite can target the default socket, Colima, or a remote daemon unchanged.

## Run it

```bash
# Full stack (API + RabbitMQ) via compose:
just up
just logs

# Or locally (needs uv, a reachable RabbitMQ, and the Docker socket):
just install
just run
```

API docs are served at `http://localhost:8448/docs`.

## Endpoints

| Method | Path                          | Purpose                                  |
|--------|-------------------------------|------------------------------------------|
| GET    | `/health`                     | Daemon ping                              |
| GET    | `/containers`                 | List live containers (from Docker)       |
| POST   | `/containers`                 | Pull + create a container                |
| GET    | `/containers/{id}`            | Live status of one container             |
| POST   | `/containers/{id}/start`      | Start (status reloaded after)            |
| POST   | `/containers/{id}/stop`       | Stop (status reloaded after)             |
| DELETE | `/containers/{id}`            | Force-remove                             |
| GET    | `/deployments`                | Deployment history (from SQLite)         |
| GET    | `/deployments/{id}`           | One deployment record                    |

### Async deploy via the queue

```bash
# Drop a deploy request on the queue; the worker pulls/creates/starts it.
just publish nginx:latest my-nginx
```

The consumer then deploys the container off the event loop and writes a
`Deployment` row with `source = "queue"`.

## Notes & next steps

- Failed queue deploys are logged and dropped (no requeue) to avoid poison-
  message loops. A production build would route them to a **dead-letter queue**.
- SQLite is fine for a single node; swap `DATABASE_URL` for Postgres to scale
  out (the SQLModel layer is unchanged).
- The natural next layer is a **SvelteKit + shadcn-svelte** dashboard consuming
  this REST API for list / create / start / stop / delete with live status.

## Security

The API is granted the host Docker socket — equivalent to root on the host.
Do not expose it publicly without authentication (JWT/OpenAuth) and network
controls in front of it.
