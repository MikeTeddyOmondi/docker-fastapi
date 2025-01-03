import json
from aio_pika import connect
import aio_pika
import pika

# from datetime import datetime
from docker import DockerClient

docker_client = DockerClient()


async def consume_build_queue(
    connection: aio_pika.RobustConnection, 
    queue_name="locci-deploy"
):
    # channel = connection.channel()
    # channel.queue_declare(queue=queue_name, durable=True)

    # # Perform connection
    # connection = await connect("amqp://guest:guest@localhost/")

    async with connection:
        # Creating a channel
        channel = await connection.channel()
        channel.set_qos(prefetch_count=1)
        # Declaring queue
        queue = await channel.declare_queue(queue_name, durable=True)

        # async with queue.iterator() as queue_iter:
        #     # Cancel consuming after __aexit__
        #     async for message in queue_iter:
        #         async with message.process():
        #             # print(message.body)
        #             # if queue.name in message.body.decode():
        #             #     break
        #             decodedMsg = json.loads(message.body.decode())
        #             print("[x] RabbitMQ message received: %r" % decodedMsg)
        #             docker_client.images.pull(decodedMsg["image"])
        #             container = docker_client.containers.create(
        #                 decodedMsg["image"], name=decodedMsg["name"], ports={"3000/tcp": 3000}
        #             )
        #             container = docker_client.containers.get(container.container_id)
        #             container.start()
        #             break

    def callback(ch, method, properties, body):
        decodedMsg = json.loads(body.decode())
        print("[x] RabbitMQ message received: %r" % decodedMsg)
        # Insert record to database
        try:
            # Pull, create & start the container
            # docker_client.images.pull(decodedMsg.image)
            # container = docker_client.containers.create(
            #     decodedMsg.image, name=decodedMsg.name, ports={"3000/tcp": 3000}
            # )
            # container = docker_client.containers.get(container.container_id)
            # container.start()

            docker_client.images.pull(decodedMsg["image"])
            container = docker_client.containers.create(
                decodedMsg["image"], name=decodedMsg["name"], ports={"3000/tcp": 3000}
            )
            container = docker_client.containers.get(container.container_id)
            container.start()
            return dict(
                content={"id": container.container_id, "status": container.status}
            )
        except Exception as e:
            raise Exception(detail=str(e.__dict__["explanation"]))

    # channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)
    await queue.consume(on_message=callback, no_ack=True)


def send_build_message(
    connection: pika.BlockingConnection, body_message: str, queue_name="locci-build"
):
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)
    channel.basic_publish(exchange="", routing_key="/locci-build", body=body_message)
    print("[x] Sent RabbitMQ message!'")
    connection.close()


async def rabbitmq_connection(loop):
    # credentials = pika.PlainCredentials("user", "password")
    # connection = pika.BlockingConnection(
    #     pika.ConnectionParameters(host="172.17.0.1", port=5672, credentials=credentials)
    # )

    # Perform connection
    # connection = await connect("amqp://guest:guest@localhost/")
    connection = await aio_pika.connect_robust(
        "amqp://user:password@127.0.0.1/", loop=loop
    )

    return connection
