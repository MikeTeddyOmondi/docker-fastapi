default:
    just --list

run:
    fastapi dev app/main.py

build-image:
    docker build -t ranckosolutionsinc/docker-api:v1.0 .

start-app:
    docker run -dp 8448:80 -v "/var/run/docker.sock:/var/run/docker.sock" --name docker-api ranckosolutionsinc/docker-api:v1.0 

logs:
    docker logs -f docker-api    

stop-app:
    docker stop docker-api

remove-app:
    docker rm docker-api

clean-up:
    just stop-app
    just remove-app
    
