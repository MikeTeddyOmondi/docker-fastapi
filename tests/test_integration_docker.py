"""End-to-end lifecycle test against a real Docker daemon.

Runs the full create -> start -> stop -> delete flow through the HTTP layer and
asserts the SQLite audit log tracks it. Uses the real ``docker_service`` client,
so it honours DOCKER_HOST (e.g. point it at Colima):

    DOCKER_HOST="unix://$HOME/.colima/default/docker.sock" \
        uv run pytest -m integration

Auto-skips when no daemon is reachable, so the default suite stays hermetic.
"""

import time

import pytest

import app.docker_service as docker

# A tiny image with a real entrypoint so create/start/stop are meaningful.
IMAGE = "hello-world"


def _daemon_reachable() -> bool:
    try:
        return bool(docker.ping())
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _daemon_reachable(), reason="no reachable Docker daemon (set DOCKER_HOST)"
    ),
]


def test_full_container_lifecycle(client):
    name = f"smoke-{int(time.time())}"

    assert client.get("/health").json() == {"status": "ok"}

    created = client.post("/containers", json={"image": IMAGE, "name": name})
    assert created.status_code == 201
    cid = created.json()["id"]

    try:
        assert client.get(f"/containers/{cid}").status_code == 200

        assert client.post(f"/containers/{cid}/start").status_code == 200
        assert client.post(f"/containers/{cid}/stop").status_code == 200

        # Persisted to the audit log via the API path.
        record = client.get(f"/deployments/{cid}").json()
        assert record["source"] == "api"
        assert record["name"] == name
    finally:
        assert client.delete(f"/containers/{cid}").status_code == 200

    # Deletion is recorded, not erased.
    assert client.get(f"/deployments/{cid}").json()["status"] == "deleted"
    # And it's gone from the live daemon.
    assert client.get(f"/containers/{cid}").status_code == 404
