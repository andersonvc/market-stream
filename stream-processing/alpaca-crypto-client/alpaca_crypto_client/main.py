import logging
import os

from dotenv import load_dotenv

from alpaca_subscriber import L2CryptoDataStream
from producer import KafkaProducerClient

logging.basicConfig(level=logging.INFO)
load_dotenv(verbose=True)

if __name__ == "__main__":

    kafka_producer = KafkaProducerClient(
        kafka_broker_url=os.getenv(
            "KAFKA_BROKER_URL", "localhost:9092,localhost:9093,localhost:9094"
        ),
        schema_registry_url=os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:8084"),
    )

    orderbook_handler = kafka_producer.kafka_producer_handler(
        topic_name="cryptoOrderbook",
        avro_schema_name="cryptoOrderbook-value",
    )

    alpaca_crypto_client = L2CryptoDataStream(
        api_key=os.getenv("ALPACA_API_KEY"),
        secret_key=os.getenv("ALPACA_API_SECRET"),
    )

    symbols = "BTC/USD"
    alpaca_crypto_client.subscribe_orderbook(orderbook_handler, symbols)
    alpaca_crypto_client.run()
