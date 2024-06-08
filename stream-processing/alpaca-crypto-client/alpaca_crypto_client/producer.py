import functools
import io
import json
import logging
import time

from avro.io import DatumWriter, BinaryEncoder
import confluent_kafka
from confluent_kafka.avro.cached_schema_registry_client import (
    CachedSchemaRegistryClient,
)

logging.basicConfig(level=logging.INFO)


def default_kafka_publisher_callback(err, msg):
    """Called once for each message produced to indicate delivery result.
    Triggered by poll() or flush().
    """
    if err is not None:
        logging.warning(f"Message to {msg.topic()} delivery failed: {err}")


def encode_avro_msg(record, schema):
    writer = DatumWriter(schema)
    bout = io.BytesIO()
    encoder = BinaryEncoder(bout)

    if isinstance(record, str):
        record = json.loads(record)
    elif not isinstance(record, dict):
        record = record.model_dump()

    writer.write(record, encoder)
    data = bout.getvalue()
    return data


class KafkaProducerClient:
    """
    Configure an interface handler for publishing messages to our Kafka broker. The kafka_producer_handler method returns a partial
    that can be used as a wrapper to publish messages from a websocket listener (e.g. Alpaca) to a configured Kafka broker.
    """

    def __init__(self, kafka_broker_url, schema_registry_url):
        self.kafka_producer = confluent_kafka.Producer(
            {"bootstrap.servers": kafka_broker_url}
        )

        max_retry_attempts = 6
        while retry_cnt := 0 < max_retry_attempts:
            try:
                self.schema_registry = CachedSchemaRegistryClient(
                    {"url": schema_registry_url}, 5
                )
                break
            except:
                retry_cnt += 1
                logging.error(
                    f"Failed to connect to schema registry. Retrying {retry_cnt} of {max_retry_attempts}"
                )
                time.sleep(5 + 3**retry_cnt)

        if not self.schema_registry:
            raise Exception("Failed to connect to schema registry")

        self.schema_map = {}

        self.poll_frequency = 150
        self.poll_offset = 0

    def _configure_schema(self, avro_schema_name, version=None):
        # Load the stored AVRO schema from the schema registry into this class' schema map

        max_retry_attempts = 6
        while retry_cnt := 0 < max_retry_attempts:
            try:
                schema = self.schema_registry.get_latest_schema(avro_schema_name)[1]
                assert schema, f"Empty schema: {avro_schema_name} (retrying)" 
                self.schema_map[avro_schema_name] = schema
                return
            except Exception as e:
                retry_cnt += 1
                logging.error(
                    f"Failed to register schema: {avro_schema_name}. Retrying {retry_cnt} of {max_retry_attempts}\n{e}"
                )
                time.sleep(5 + 3**retry_cnt)
        if not self.schema_map.get(avro_schema_name):
            raise Exception(f"Failed to register schema: {avro_schema_name}")

    async def _publish_message_to_kafka(
        self, message, kafka_producer, topic_name, avro_schema, config
    ):
        # Compress message to AVRO format based on schema and publish to Kafka topic. (Optionally, specify callback operation)

        # Encode message to AVRO format
        compressed_msg = encode_avro_msg(message, avro_schema)

        # Specify custom callback operation to execute when message is delivered successfully or raises exception
        callback_partial = config["callback"] if config["enable_callback"] else None

        # Publish AVRO message to Kafka broker
        kafka_producer.produce(
            topic_name, value=compressed_msg, callback=callback_partial
        )
        self.poll_offset = (self.poll_offset + 1) % self.poll_frequency
        if self.poll_offset == 0:
            kafka_producer.poll(0)

    def kafka_producer_handler(self, topic_name, avro_schema_name, config=None):

        # Assign default configurations for publishing message to Kakfa broker
        default_config = {
            "enable_callback": True,
            "callback": default_kafka_publisher_callback,
        }
        config = {**default_config, **(config or {})}

        # Load schema; grab from schema_registry if not already loaded
        if avro_schema_name or not self.schema_map.get(avro_schema_name, None):
            self._configure_schema(avro_schema_name)
        avro_schema = self.schema_map.get(avro_schema_name)


        handler = functools.partial(
            self._publish_message_to_kafka,
            kafka_producer=self.kafka_producer,
            topic_name=topic_name,
            avro_schema=avro_schema,
            config=config,
        )

        return handler
