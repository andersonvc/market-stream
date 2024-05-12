from functools import lru_cache, partial
import logging
import os
import threading
import time

from avro.datafile import DataFileWriter
from avro.io import DatumWriter, DatumReader, BinaryEncoder, BinaryDecoder

from alpaca_stream import L2CryptoDataStream
from queue_interface import AvroCryptoConnector

from dotenv import load_dotenv

load_dotenv(verbose=True)
logging.basicConfig(level=logging.INFO)


@lru_cache(maxsize=5)
def init_stream_store(filepath, schema, codec='deflate'):
    if not os.path.isfile(filepath):
        DataFileWriter(open(filepath, "wb"), DatumWriter(), schema, codec=codec).close()
    return True


def stream_publisher_thread():
    """
    Connects to Alpaca's streaming Crypto feed and publishes quote/trade data to Kafka
    Currenty only listens for BTC/USD and ETH/USD events
    """
    load_dotenv()
    try:
        api_key = os.getenv('ALPACA_API_KEY')
        api_secret = os.getenv('ALPACA_API_SECRET')
    except EnvironmentError:
        logging.error('Alpaca API envvars not configured; killing service.')
        raise SystemExit

    alpaca_conn = L2CryptoDataStream(api_key,api_secret)

    kafka_connector = AvroCryptoConnector()
    logging.info('Connected to Alpaca Crypto feed')

    symbols = ['BTC/USD']
    
    topic_name = 'cryptoOrderbook'
    alpaca_conn.subscribe_orderbook(partial(kafka_connector.publish_message, topic_name=topic_name), *symbols)

    #topic_name = 'cryptoQuote'
    #alpaca_conn.subscribe_quotes(partial(kafka_connector.publish_message, topic_name=topic_name), *symbols)

    alpaca_conn.run()


def stream_consumer_thread(topic):
    """
    Connects to Kafka and consumes quote/trade data from the Alpaca Crypto feed. The consume quote operation is a generator that spits out a
    decoded quote entry. The quote entry is then written to an Avro file of the format '<TOPIC>_<YYYYMMDD>.avro'.
    """

    kafka_connector = AvroCryptoConnector()

    def create_filename(topic,timestamp_input):
        date_string = timestamp_input.strftime('%Y%m%d')
        return f"data/{topic}_{date_string}.avro"

    for msg in kafka_connector.consume_messages(topic):
        ts = msg['timestamp']
        avro_filepath = create_filename(topic, ts)
        init_stream_store(avro_filepath, schema=kafka_connector.topics[topic], codec='deflate')
        with DataFileWriter(open(avro_filepath, "ab+"), DatumWriter()) as avro_writer:
            avro_writer.append(msg)


def producer():
    t = threading.Thread(target=stream_publisher_thread)
    t.start()
    t.join()

def consumer():
    
    topics = ['cryptoOrderbook']
    threads = [ threading.Thread(target=stream_consumer_thread, args=(topic,)) for topic in topics]

    for t in threads:
        t.start()

    for t in threads:
        t.join()


if __name__ == '__main__':
    time.sleep(10)
    while True:
        try:
            producer() if os.getenv('CLIENT_TYPE','producer') == 'producer' else consumer()
        except Exception as e:
            logging.error(f"Error: {e}")
            time.sleep(60)

