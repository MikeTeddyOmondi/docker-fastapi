"""Environment-driven application settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Persistence. SQLite by default; swap DATABASE_URL for Postgres in prod.
    database_url: str = "sqlite:///./data/docker_api.db"

    # Message broker for asynchronous deploys.
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    deploy_queue: str = "locci-deploy"

    # Default port mapping applied to created containers.
    default_container_port: int = 3000

    # Docker daemon endpoint. When unset, the client falls back to
    # DockerClient.from_env() (which reads the DOCKER_HOST/TLS env vars and
    # otherwise the default unix socket). Set this to target Colima or a remote
    # daemon from a .env file. See .env.sample for the supported forms.
    docker_host: str | None = None

    cors_origins: list[str] = [
        "http://localhost",
        "http://127.0.0.1",
        "http://0.0.0.0",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
