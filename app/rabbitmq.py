"""Asynchronous RabbitMQ deploy worker (and a publisher helper).

This is the control-plane -> worker split: instead of the HTTP request doing a
slow `pull + create + start`, a producer drops a JSON message onto the durable
``locci-deploy`` queue and this consumer processes it.

Key fixes over the original:
  * uses ``container.id`` (the original referenced a non-existent
    ``container.container_id`` and would have raised AttributeError);
  * runs the blocking docker-py calls via ``asyncio.to_thread`` so they don't
    freeze the event loop;
  * acks/rejects explicitly (``requeue=False``) so a poison message is dropped
    and logged instead of redelivered forever;
  * degrades gracefully — if the broker is down at startup the API still runs.
"""

import asyncio
import json
import logging

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from . import db
from . import docker_service as docker
from .config import get_settings

settings = get_settings()
logger = logging.getLogger("docker_api.rabbitmq")


async def _handle_message(message: AbstractIncomingMessage) -> None:
    # On clean exit the message is acked; on an unhandled exception it is
    # rejected without requeue (no poison-message redelivery loop).
    async with message.process(requeue=False, ignore_processed=True):
        try:
            payload = json.loads(message.body.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("Discarding malformed message: %r", message.body[:200])
            return

        image, name = payload.get("image"), payload.get("name")
        if not image or not name:
            logger.warning("Discarding message missing image/name: %s", payload)
            return

        logger.info("Deploying from queue: image=%s name=%s", image, name)
        try:
            result = await asyncio.to_thread(docker.deploy, image, name)
        except docker.ImageUnavailable:
            logger.error("Image unavailable, dropping message: %s", image)
            return
        except docker.DockerOperationError as e:
            logger.error("Deploy failed for %s: %s", name, e.message)
            return

        await asyncio.to_thread(
            db.upsert_deployment,
            id=result["id"],
            name=result["name"],
            image=result.get("image", image),
            status=result["status"],
            source="queue",
        )
        logger.info("Deployed %s (%s)", name, result["id"])


async def start_consumer():
    """Connect, start consuming, and return the connection (or None if down)."""
    try:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    except Exception as e:  # broker unreachable at boot
        logger.warning(
            "RabbitMQ unavailable (%s); API will run without the deploy queue", e
        )
        return None

    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)
    queue = await channel.declare_queue(settings.deploy_queue, durable=True)
    await queue.consume(_handle_message)
    logger.info("Consuming deploy queue '%s'", settings.deploy_queue)
    return connection


async def shutdown_consumer(connection) -> None:
    if connection is not None:
        await connection.close()
        logger.info("RabbitMQ connection closed")


async def publish_deploy_message(image: str, name: str) -> None:
    """Publish a deploy request onto the durable queue."""
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        await channel.declare_queue(settings.deploy_queue, durable=True)
        body = json.dumps({"image": image, "name": name}).encode()
        await channel.default_exchange.publish(
            aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key=settings.deploy_queue,
        )
        logger.info("Published deploy message for %s", name)
