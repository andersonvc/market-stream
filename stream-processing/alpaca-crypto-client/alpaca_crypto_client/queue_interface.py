import io
import logging
import six
import sys

from avro.datafile import DataFileWriter
from avro.io import DatumWriter, DatumReader, BinaryEncoder, BinaryDecoder

from confluent_kafka import Consumer, Producer, KafkaError, KafkaException
from confluent_kafka.avro.cached_schema_registry_client import CachedSchemaRegistryClient

if sys.version_info >= (3, 12, 2): sys.modules['kafka.vendor.six.moves'] = six.moves


def encode_avro_msg(record, schema):
    writer = DatumWriter(schema)
    bout = io.BytesIO()
    encoder = BinaryEncoder(bout)
    writer.write(record, encoder)
    data = bout.getvalue()
    return data


def decode_avro_msg(data, schema):
    reader = DatumReader(schema)
    message_bytes = io.BytesIO(data)
    decoder = BinaryDecoder(message_bytes)
    record = reader.read(decoder)
    return record


def delivery_report(err, msg):
    """ Called once for each message produced to indicate delivery result.
        Triggered by poll() or flush(). """
    if err is not None:
       logging.warning('Message delivery failed: {}'.format(err))


class AvroCryptoConnector():

    cnt = 0

    def __init__(self, schema_registry_url='http://schema-registry:8081', kafka_servers='kafka-1:9092,kafka-2:9092,kafka-3:9092'):
        

        self.schema_registry = CachedSchemaRegistryClient({'url': schema_registry_url}, 5)

        self.producer = Producer({'bootstrap.servers': kafka_servers})
        self.consumer = Consumer({
            'bootstrap.servers': kafka_servers,
            'group.id': 'group1',
            'auto.offset.reset': 'earliest',
        })

        self.topics = {
            'cryptoQuote': self.schema_registry.get_latest_schema(subject='cryptoQuote-value')[1],
            'cryptoTrade': self.schema_registry.get_latest_schema(subject='cryptoTrade-value')[1],
            'cryptoOrderbook': self.schema_registry.get_latest_schema(subject='cryptoOrderbook-value')[1],

            'testOrderbook': self.schema_registry.get_latest_schema(subject='testOrderbook-value')[1]
        }

    async def publish_message(self, record, topic_name):

        assert topic_name in self.topics.keys(), f"Topic {topic_name} not found in predefined topics"

        if not isinstance(record, dict):
            record = record.model_dump()

        data = encode_avro_msg(record, self.topics[topic_name])
        self.producer.produce(topic_name, data, callback=delivery_report)
        self.producer.poll(0)

    def consume_messages(self, topic_name):

        assert topic_name in self.topics.keys(), f"Topic {topic_name} not found in predefined topics"
        self.consumer.subscribe([topic_name])
        while True:
            msg = self.consumer.poll(0.0)
            if not msg:
                continue
            
            if msg.error():
                logging.warning(f"Consumer error: {msg.error()}")
                continue
            extract = decode_avro_msg(msg.value(), self.topics[topic_name])
            self.consumer.commit()
            yield extract
