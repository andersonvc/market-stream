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


def stream_publisher_thread():
    """
    Connects to Alpaca's streaming Crypto feed and publishes quote/trade data to Kafka
    Currenty only listens for BTC/USD and ETH/USD events
    """
    load_dotenv()
    print(os.getenv('ALPACA_API_KEY'))
    try:
        api_key = os.getenv('ALPACA_API_KEY')
        api_secret = os.getenv('ALPACA_API_SECRET')
    except EnvironmentError:
        logging.error('Alpaca API envvars not configured; killing service.')
        raise SystemExit

    conn = L2CryptoDataStream(api_key,api_secret)

    kafka_connector = AvroCryptoConnector()
    logging.info('Connected to Alpaca Crypto feed')

    symbols = ['BTC/USD']
    #conn.subscribe_quotes(kafka_connector.publish_quote, *symbols)
    #conn.subscribe_trades(kafka_connector.publish_trade, *symbols)
    conn.subscribe_orderbook(kafka_connector.publish_orderbook, *symbols)
    #conn.get_latest_cypto_orderbook(kafka_connector.publish_orderbook, *symbols)
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

    #for quote in kafka_connector.consume_quote():
    #    quote_filepath = create_filename('quote', quote['timestamp'])
    #    with DataFileWriter(open(quote_filepath, "ab+"), DatumWriter(), kafka_connector.quote_schema, codec='deflate') as quote_writer:
    #        quote_writer.append(quote)

    for orderbook in kafka_connector.consume_orderbook():
        orderbook_filepath = create_filename('orderbook', orderbook['timestamp'])
        with DataFileWriter(open(orderbook_filepath, "ab+"), DatumWriter(), kafka_connector.orderbook_schema, codec='deflate') as orderbook_writer:
            orderbook_writer.append(orderbook)


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

