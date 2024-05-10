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
    quote_topic = 'cryptoQuote'
    trade_topic = 'cryptoTrade'
    orderbook_topic = 'cryptoOrderbook'

    def __init__(self, schema_registry_url='http://schema-registry:8081', kafka_servers='kafka-1:9092,kafka-2:9092,kafka-3:9092'):
        

        self.schema_registry = CachedSchemaRegistryClient({'url': schema_registry_url}, 5)

        self.producer = Producer({'bootstrap.servers': kafka_servers})
        self.consumer = Consumer({
            'bootstrap.servers': kafka_servers,
            'group.id': 'group1',
            'auto.offset.reset': 'earliest',
        })

        self.quote_schema = self.schema_registry.get_latest_schema(subject=f'{self.quote_topic}-value')[1]
        self.trade_schema = self.schema_registry.get_latest_schema(subject=f'{self.trade_topic}-value')[1]
        self.orderbook_schema = self.schema_registry.get_latest_schema(subject=f'{self.orderbook_topic}-value')[1]


    async def publish_quote(self, quote_dict):
        quote_dict = quote_dict.model_dump()
        quote_subset = {'timestamp', 'symbol', 'bid_price', 'ask_price', 'bid_size', 'ask_size'}
        quote_dict = {k: v for k, v in quote_dict.items() if k in quote_subset}

        try:
            data = encode_avro_msg(quote_dict, self.quote_schema)
        except:
            self.quote_schema = self.schema_registry.get_latest_schema(subject=f'{self.quote_topic}-value')[1]
            data = encode_avro_msg(quote_dict, self.quote_schema)
        
        self.producer.produce(self.quote_topic, data, callback=delivery_report)
        self.producer.poll(0)

    
    async def publish_trade(self, trade_dict):
        trade_dict = trade_dict.model_dump()

        trade_dict['id'] = trade_dict.get('id',0)
        trade_subset = {'timestamp', 'symbol', 'price', 'size', 'id'}
        trade_dict = {k: v for k, v in trade_dict.items() if k in trade_subset}

        try:
            data = encode_avro_msg(trade_dict, self.trade_schema)
        except:
            self.trade_schema = self.schema_registry.get_latest_schema(subject=f'{self.trade_topic}-value')[1]
            data = encode_avro_msg(trade_dict, self.trade_schema)
        self.producer.produce(self.trade_topic, data, callback=delivery_report)

        self.producer.poll(0)

    
    async def publish_orderbook(self, orderbook_dict):
        orderbook_dict = orderbook_dict.model_dump()
        #orderbook_subset = {'timestamp', 'symbol', 'bids', 'asks'}
        #orderbook_dict = {k: v for k, v in orderbook_dict.items() if k in orderbook_subset}

        try:
            data = encode_avro_msg(orderbook_dict, self.orderbook_schema)
        except:
            self.orderbook_schema = self.schema_registry.get_latest_schema(subject=f'{self.orderbook_topic}-value')[1]
            data = encode_avro_msg(orderbook_dict, self.orderbook_schema)
        self.producer.produce(self.orderbook_topic, data, callback=delivery_report)
        logging.warning(f"Orderbook: {orderbook_dict}")


    def consume_quote(self, decode_msg=True):
        
        self.consumer.subscribe([self.quote_topic])
        while True:
            msg = self.consumer.poll(0.0)
            if not msg:
                continue
            if msg.error():
                logging.warning(f"Consumer error: {msg.error()}")
                continue
            try:
                extract = decode_avro_msg(msg.value(), self.quote_schema) if decode_msg else msg.value()
            except:
                self.quote_schema = self.schema_registry.get_latest_schema(subject=f'{self.quote_topic}-value')[1]
                extract = decode_avro_msg(msg.value(), self.quote_schema) if decode_msg else msg.value()
            self.consumer.commit()
            yield extract
    
    def consume_orderbook(self, decode_msg=True):
        
        self.consumer.subscribe([self.orderbook_topic])
        while True:
            msg = self.consumer.poll(0.0)
            if not msg:
                continue
            if msg.error():
                logging.warning(f"Consumer error: {msg.error()}")
                continue
            try:
                extract = decode_avro_msg(msg.value(), self.orderbook_schema) if decode_msg else msg.value()
            except:
                self.quote_schema = self.schema_registry.get_latest_schema(subject=f'{self.orderbook_topic}-value')[1]
                extract = decode_avro_msg(msg.value(), self.quote_schema) if decode_msg else msg.value()
            self.consumer.commit()
            yield extract