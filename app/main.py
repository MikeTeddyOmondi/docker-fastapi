"""FastAPI control plane for Docker containers.

Layering:
  routes (this file)  ->  docker_service (Docker)  +  db (SQLite persistence)

Routes are plain ``def`` (not ``async def``): docker-py is blocking, so running
in FastAPI's threadpool keeps the event loop free for the RabbitMQ consumer.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import db
from . import docker_service as docker
from .config import get_settings
from .models import ContainerCreateRequest
from .rabbitmq import shutdown_consumer, start_consumer

logging.basicConfig(level=logging.INFO)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    consumer = await start_consumer()
    try:
        yield
    finally:
        await shutdown_consumer(consumer)


app = FastAPI(title="Docker Control Plane API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    docker.ping()
    return {"status": "ok"}


# --------------------------------------------------------------------------- #
# Live container operations (Docker is the source of truth)
# --------------------------------------------------------------------------- #
@app.get("/containers")
def list_containers():
    return docker.list_containers()


@app.post("/containers", status_code=201)
def create_container(request: ContainerCreateRequest):
    try:
        result = docker.create_container(request.image, request.name)
    except docker.ImageUnavailable as e:
        raise HTTPException(status_code=404, detail=f"image not found: {e}")
    except docker.DockerOperationError as e:
        raise HTTPException(status_code=500, detail=e.message)

    db.upsert_deployment(
        id=result["id"],
        name=result["name"],
        image=result["image"],
        status=result["status"],
        source="api",
    )
    return result


@app.get("/containers/{container_id}")
def get_container(container_id: str):
    try:
        return docker.get_container(container_id)
    except docker.ContainerNotFound:
        raise HTTPException(status_code=404, detail="container not found")
    except docker.DockerOperationError as e:
        raise HTTPException(status_code=500, detail=e.message)


@app.post("/containers/{container_id}/start")
def start_container(container_id: str):
    try:
        result = docker.start_container(container_id)
    except docker.ContainerNotFound:
        raise HTTPException(status_code=404, detail="container not found")
    except docker.DockerOperationError as e:
        raise HTTPException(status_code=500, detail=e.message)

    db.update_status(container_id, result["status"])
    return result


@app.post("/containers/{container_id}/stop")
def stop_container(container_id: str):
    try:
        result = docker.stop_container(container_id)
    except docker.ContainerNotFound:
        raise HTTPException(status_code=404, detail="container not found")
    except docker.DockerOperationError as e:
        raise HTTPException(status_code=500, detail=e.message)

    db.update_status(container_id, result["status"])
    return result


@app.delete("/containers/{container_id}")
def delete_container(container_id: str):
    try:
        result = docker.delete_container(container_id)
    except docker.ContainerNotFound:
        raise HTTPException(status_code=404, detail="container not found")
    except docker.DockerOperationError as e:
        raise HTTPException(status_code=500, detail=e.message)

    db.mark_deleted(container_id)
    return result


# --------------------------------------------------------------------------- #
# Deployment history (SQLite-backed audit log)
# --------------------------------------------------------------------------- #
@app.get("/deployments")
def list_deployments():
    return db.list_deployments()


@app.get("/deployments/{container_id}")
def get_deployment(container_id: str):
    record = db.get_deployment(container_id)
    if record is None:
        raise HTTPException(status_code=404, detail="deployment not found")
    return record
