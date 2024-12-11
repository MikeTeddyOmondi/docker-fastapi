import pika

# from datetime import datetime
from docker import DockerClient

docker_client = DockerClient()


def consume_build_queue(
    connection: pika.BlockingConnection, queue_name="locci-deploy"
):
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)

    def callback(ch, method, properties, body):
        decodedMsg = body.decode()
        print("[x] RabbitMQ message received: %r" % decodedMsg)
        # Insert record to database
        try:
            # Pull, create & start the container
            docker_client.images.pull(decodedMsg.image)
            container = docker_client.containers.create(
                decodedMsg.image, name=decodedMsg.name, ports={"3000/tcp": 3000}
            )
            container = docker_client.containers.get(container.container_id)
            container.start()
            return dict(
                content={"id": container.container_id, "status": container.status}
            )
        except Exception as e:
            raise Exception(detail=str(e.__dict__["explanation"]))

    channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)


def send_build_message(
    connection: pika.BlockingConnection, body_message: str, queue_name="locci-build"
):
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)
    channel.basic_publish(exchange="", routing_key="/locci-build", body=body_message)
    print("[x] Sent RabbitMQ message!'")
    connection.close()


def rabbitmq_connection():
    credentials = pika.PlainCredentials("user", "password")
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host="localhost", port=5672, credentials=credentials)
    )
    return connection
