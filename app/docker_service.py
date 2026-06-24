"""Thin wrapper around docker-py.

docker-py is *synchronous and blocking* — there is nothing to await on its
calls. This module keeps all Docker interaction in one place, translates
docker-py exceptions into typed domain errors, and (critically) calls
``reload()`` after state-changing operations so the returned status reflects
the daemon's real state instead of a stale local snapshot.
"""

from docker import DockerClient
from docker.errors import APIError, ImageNotFound, NotFound

from .config import get_settings

settings = get_settings()

# The client is created lazily on first use rather than at import time, so the
# module (and the whole app) can be imported and unit-tested without a running
# daemon. An explicit DOCKER_HOST (from settings/.env) wins; otherwise we fall
# back to from_env(), which honours DOCKER_HOST/DOCKER_TLS_VERIFY/DOCKER_CERT_PATH
# in the process environment and finally the default unix socket. Either way the
# same image works against the default socket, Colima, or a remote daemon.
_client: DockerClient | None = None


def get_client() -> DockerClient:
    global _client
    if _client is None:
        if settings.docker_host:
            _client = DockerClient(base_url=settings.docker_host)
        else:
            _client = DockerClient.from_env()
    return _client


# --------------------------------------------------------------------------- #
# Domain errors (decoupled from docker-py internals)
# --------------------------------------------------------------------------- #
class ContainerNotFound(Exception):
    pass


class ImageUnavailable(Exception):
    pass


class DockerOperationError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _safe_detail(e: APIError) -> str:
    # Not every APIError carries `.explanation`; fall back to str(e).
    return getattr(e, "explanation", None) or str(e)


def _image_tag(container) -> str:
    image = getattr(container, "image", None)
    if image is None:
        return "unknown"
    tags = image.tags
    return tags[0] if tags else (image.id or "unknown")


# --------------------------------------------------------------------------- #
# Operations
# --------------------------------------------------------------------------- #
def ping() -> bool:
    try:
        return get_client().ping()
    except APIError as e:
        raise DockerOperationError(_safe_detail(e)) from e


def list_containers() -> list[dict]:
    return [
        {
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "image": _image_tag(c),
        }
        for c in get_client().containers.list(all=True)
    ]


def create_container(image: str, name: str) -> dict:
    try:
        get_client().images.pull(image)
        port = settings.default_container_port
        container = get_client().containers.create(
            image, name=name, ports={f"{port}/tcp": port}
        )
        return {
            "id": container.id,
            "name": container.name,
            "status": container.status,
            "image": image,
        }
    except ImageNotFound as e:
        raise ImageUnavailable(image) from e
    except APIError as e:
        raise DockerOperationError(_safe_detail(e)) from e


def get_container(container_id: str) -> dict:
    try:
        c = get_client().containers.get(container_id)
        return {"id": c.id, "name": c.name, "status": c.status}
    except NotFound as e:
        raise ContainerNotFound(container_id) from e
    except APIError as e:
        raise DockerOperationError(_safe_detail(e)) from e


def start_container(container_id: str) -> dict:
    try:
        c = get_client().containers.get(container_id)
        c.start()
        c.reload()  # re-inspect so .status is current
        return {
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "image": _image_tag(c),
        }
    except NotFound as e:
        raise ContainerNotFound(container_id) from e
    except APIError as e:
        raise DockerOperationError(_safe_detail(e)) from e


def stop_container(container_id: str) -> dict:
    try:
        c = get_client().containers.get(container_id)
        c.stop()
        c.reload()  # re-inspect so .status is current
        return {
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "image": _image_tag(c),
        }
    except NotFound as e:
        raise ContainerNotFound(container_id) from e
    except APIError as e:
        raise DockerOperationError(_safe_detail(e)) from e


def delete_container(container_id: str) -> dict:
    try:
        c = get_client().containers.get(container_id)
        c.remove(force=True)
        return {"id": container_id, "status": "deleted"}
    except NotFound as e:
        raise ContainerNotFound(container_id) from e
    except APIError as e:
        raise DockerOperationError(_safe_detail(e)) from e


def deploy(image: str, name: str) -> dict:
    """Pull, create, and start a container in one step (used by the worker)."""
    created = create_container(image, name)
    return start_container(created["id"])
