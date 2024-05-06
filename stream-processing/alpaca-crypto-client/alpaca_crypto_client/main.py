import io
import logging
import os
import six
import sys
import threading
import time

from alpaca.data.live.crypto import CryptoDataStream
from alpaca.trading.client import TradingClient

from avro.datafile import DataFileWriter
from avro.io import DatumWriter, DatumReader, BinaryEncoder, BinaryDecoder

from confluent_kafka import Consumer, Producer, KafkaError, KafkaException
from confluent_kafka.avro.cached_schema_registry_client import CachedSchemaRegistryClient

from dotenv import load_dotenv

if sys.version_info >= (3, 12, 2): sys.modules['kafka.vendor.six.moves'] = six.moves

load_dotenv(verbose=True)
logging.basicConfig(level=logging.INFO)


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

    quote_topic = 'cryptoQuote'
    trade_topic = 'cryptoTrade'

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


def stream_publisher_thread():
    """
    Connects to Alpaca's streaming Crypto feed and publishes quote/trade data to Kafka
    Currenty only listens for BTC/USD and ETH/USD events
    """
    try:
        api_key = os.getenv('ALPACA_API_KEY')
        api_secret = os.getenv('ALPACA_API_SECRET')
    except EnvironmentError:
        logging.error('Alpaca API envvars not configured; killing service.')
        raise SystemExit

    conn = CryptoDataStream(api_key,api_secret)

    kafka_connector = AvroCryptoConnector()

    symbols = ['BTC/USD', 'ETH/USD']
    conn.subscribe_quotes(kafka_connector.publish_quote, *symbols)
    conn.subscribe_trades(kafka_connector.publish_trade, *symbols)
    conn.run()


def stream_consumer_thread():
    """
    Connects to Kafka and consumes quote/trade data from the Alpaca Crypto feed. The consume quote operation is a generator that spits out a
    decoded quote entry. The quote entry is then written to an Avro file of the format '<TOPIC>_<YYYYMMDD>.avro'.
    """

    kafka_connector = AvroCryptoConnector()

    def create_filename(topic,timestamp_input):
        date_string = timestamp_input.strftime('%Y%m%d')
        return f"data/{topic}_{date_string}.avro"

    for quote in kafka_connector.consume_quote():
        quote_filepath = create_filename('quote', quote['timestamp'])
        with DataFileWriter(open(quote_filepath, "ab+"), DatumWriter(), kafka_connector.quote_schema, codec='deflate') as quote_writer:
            quote_writer.append(quote)


def producer():
    t = threading.Thread(target=stream_publisher_thread)
    t.start()
    t.join()

def consumer():
    stream_consumer_thread()

def main():

    threads = [
        threading.Thread(target=stream_publisher_thread),
        #threading.Thread(target=stream_consumer_thread), # moving the consumer to a seperate service
    ]

    for t in threads:
        t.start()

    for t in threads:
        t.join()


if __name__ == '__main__':
    time.sleep(20)
    while True:
        try:
            producer() if os.getenv('CLIENT_TYPE','producer') == 'producer' else consumer()
        except Exception as e:
            logging.error(f"Error: {e}")
            time.sleep(60)

