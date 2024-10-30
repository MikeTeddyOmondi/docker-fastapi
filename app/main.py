from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from docker import DockerClient
from pydantic import BaseModel

app = FastAPI()
docker_client = DockerClient()

origins = [
    "http://localhost",
    "http://0.0.0.0",
    "http://127.0.0.1",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ContainerCreateRequest(BaseModel):
    image: str
    name: str


@app.post("/containers")
async def create_container(request: ContainerCreateRequest):
    try:
        container = docker_client.containers.create(
            request.image, name=request.name, ports={"3000/tcp": 3000}
        )
        return JSONResponse(content={"id": container.id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e.__dict__["explanation"]))


@app.get("/containers/{container_id}")
async def get_container(container_id: str):
    try:
        container = docker_client.containers.get(container_id)
        return JSONResponse(content={"id": container.id, "status": container.status})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e.__dict__["explanation"]))


@app.delete("/containers/{container_id}")
async def delete_container(container_id: str):
    try:
        container = docker_client.containers.get(container_id)
        container.remove(force=True)
        return JSONResponse(content={"id": container_id, "status": "deleted"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e.__dict__["explanation"]))


@app.post("/containers/{container_id}/start")
async def start_container(container_id: str):
    try:
        container = docker_client.containers.get(container_id)
        container.start()
        return JSONResponse(content={"id": container_id, "status": container.status})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e.__dict__["explanation"]))


@app.post("/containers/{container_id}/stop")
async def stop_container(container_id: str):
    try:
        container = docker_client.containers.get(container_id)
        container.stop()
        return JSONResponse(content={"id": container_id, "status": container.status})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e.__dict__["explanation"]))
