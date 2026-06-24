"""Route + persistence tests with the Docker layer stubbed.

These exercise the wiring that the refactor is really about: error-to-HTTP
mapping and the SQLite audit log. ``app.docker_service`` is monkeypatched so no
daemon is required; the typed domain exceptions stay real so the route's
except-clauses are genuinely exercised.
"""

import app.docker_service as docker


def test_health_ok(client, monkeypatch):
    monkeypatch.setattr(docker, "ping", lambda: True)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_create_persists_deployment(client, monkeypatch):
    monkeypatch.setattr(
        docker,
        "create_container",
        lambda image, name: {
            "id": "abc123",
            "name": name,
            "image": image,
            "status": "created",
        },
    )

    r = client.post("/containers", json={"image": "nginx:latest", "name": "web"})
    assert r.status_code == 201
    assert r.json()["id"] == "abc123"

    # The audit log should now carry the record, tagged source=api.
    record = client.get("/deployments/abc123").json()
    assert record["status"] == "created"
    assert record["source"] == "api"
    assert {d["id"] for d in client.get("/deployments").json()} == {"abc123"}


def test_create_unknown_image_returns_404(client, monkeypatch):
    def _raise(image, name):
        raise docker.ImageUnavailable(image)

    monkeypatch.setattr(docker, "create_container", _raise)
    r = client.post("/containers", json={"image": "nope:404", "name": "x"})
    assert r.status_code == 404
    assert "image not found" in r.json()["detail"]


def test_get_missing_container_returns_404(client, monkeypatch):
    def _raise(container_id):
        raise docker.ContainerNotFound(container_id)

    monkeypatch.setattr(docker, "get_container", _raise)
    assert client.get("/containers/deadbeef").status_code == 404


def test_docker_failure_maps_to_500(client, monkeypatch):
    def _raise(container_id):
        raise docker.DockerOperationError("daemon exploded")

    monkeypatch.setattr(docker, "get_container", _raise)
    r = client.get("/containers/whatever")
    assert r.status_code == 500
    assert r.json()["detail"] == "daemon exploded"


def test_lifecycle_updates_status(client, monkeypatch):
    monkeypatch.setattr(
        docker,
        "create_container",
        lambda image, name: {
            "id": "c1",
            "name": name,
            "image": image,
            "status": "created",
        },
    )
    monkeypatch.setattr(
        docker,
        "start_container",
        lambda cid: {"id": cid, "name": "web", "status": "running"},
    )
    monkeypatch.setattr(
        docker, "delete_container", lambda cid: {"id": cid, "status": "deleted"}
    )

    client.post("/containers", json={"image": "nginx", "name": "web"})

    client.post("/containers/c1/start")
    assert client.get("/deployments/c1").json()["status"] == "running"

    client.delete("/containers/c1")
    assert client.get("/deployments/c1").json()["status"] == "deleted"


def test_get_unknown_deployment_returns_404(client):
    assert client.get("/deployments/missing").status_code == 404
