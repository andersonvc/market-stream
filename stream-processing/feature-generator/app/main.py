import faust
from schema_registry.client import SchemaRegistryClient, schema
from schema_registry.serializers.faust import FaustSerializer
import fastavro
import logging
from yarl import URL
import os
import io
import time
from enum import Enum

while True:
    try:
        # Register kafka brokers
        kafka_server_urls = os.getenv('KAFKA_SERVER_URL', 'kafka://kafka-1:9092,kafka://kafka-2:9092,kafka://kafka-3:9092')
        kafka_server_urls = [URL(v) for v in kafka_server_urls.split(',')]

        # Load schemas from schema registry
        schema_registry_url = os.getenv("SCHEMA_REGISTRY_URL", 'http://schema-registry:8084')
        schema_client = SchemaRegistryClient(url=schema_registry_url)

        # Register cryptoOrderbook schema
        topic = 'cryptoOrderbook'
        schema_text = schema_client.get_schema(f'{topic}-value', version='latest').schema
        orderbook_schema = fastavro.parse_schema(schema_text.flat_schema)

        # Register kafka topics
        app = faust.App('lob-aggregator', broker=kafka_server_urls)
        crypto_orderbook_topic = app.topic(topic, value_serializer='raw')
        break
    except:
        time.sleep(10)
        continue


class OrderbookAggregator:
    def __init__(self):
        self.live_orderbook_bids = {}
        self.live_orderbook_asks = {}
        self.init_state = 'unset'
    
    def handle_initialization(self, data):
        """
        Ensure the orderbook has been fully populated before publishing feature data. 
        """

        # Only start populating data when a full orderbook message is passed
        if self.init_state=='unset':
            self.live_orderbook_asks = {}
            self.live_orderbook_bids = {}
            if data.get('is_full'):
                self.init_state = 'updating'

        # New full orderbook message sent, likely error with producer
        elif self.init_state=='set' and data.get('is_full')==True:
            self.live_orderbook_asks = {}
            self.live_orderbook_bids = {}
            self.init_state = 'updating'

        # Orderbook is being updated; when the full orderbook is sent, partial updates will begin getting sent
        elif self.init_state=='updating':
            if not data.get('is_full'):
                self.init_state = 'set'
        
        # Orderbook is in an invalid / partial state
        else:
            return
    
    def is_publishable(self):
        """
        Check if the orderbook is in a valid state to publish feature data.
        """
        return self.init_state=='set' and self.live_orderbook_bids and self.live_orderbook_asks
    
    def is_updateable(self):
        """
        Check if the orderbook is in a valid state to update.
        """
        return self.init_state=='set' or self.init_state=='updating'


    def update_orderbook(self, data):

        self.handle_initialization(data)
        if not self.is_updateable():
            return

        logging.warning('updating')
        for quote in data.get('bids',[]):
            if quote['size'] <= 1e-5:
                self.live_orderbook_bids.pop(quote['price'], None)
            self.live_orderbook_bids[quote['price']] = quote['size']
        
        for quote in data.get('asks',[]):
            if quote['size'] <= 1e-5:
                self.live_orderbook_asks.pop(quote['price'], None)
            self.live_orderbook_asks[quote['price']] = quote['size']

    def get_orderbook(self):
        if not self.is_publishable():
            return

        rec = {}

        sorted_bids = sorted(self.live_orderbook_bids.items(), reverse=True)
        sorted_asks = sorted(self.live_orderbook_asks.items(), reverse=False)

        rec['spread'] = sorted_asks[0][0] - sorted_bids[0][0]
        rec['midpoint'] = (sorted_bids[0][0] + sorted_asks[0][0]) / 2
        rec['highest_bid'] = sorted_bids[0][0]
        rec['lowest_ask'] = sorted_asks[0][0]

        for label,val in {'1pct':0.01,'3pct':0.03,'5pct':0.05,'10pct':0.1}.items():
            lower_thresh = rec['midpoint']-val*rec['midpoint']
            upper_thresh = rec['midpoint']+val*rec['midpoint']
            bid_vol,ask_vol = 0.,0.
            for entry in sorted_bids:
                if entry[0] <= lower_thresh:
                    break
                bid_vol += entry[1]
                
            for entry in sorted_asks:
                if entry[0] > upper_thresh:
                    break
                ask_vol += entry[1]
            rec[f'bid_vol_{label}'] = bid_vol
            rec[f'ask_vol_{label}'] = ask_vol
            rec[f'imbalance_{label}'] = 0.0 if ask_vol==0 else ask_vol / bid_vol
            
        logging.warning('Snapshot:')
        for key,value in rec.items():
            logging.warning(f'\t{key}: {value}')
        logging.warning('\n')

orderbook = OrderbookAggregator()



@app.agent(crypto_orderbook_topic)
async def orderbook_stream(stream):
    async for entry in stream:
        data = fastavro.schemaless_reader(io.BytesIO(entry), orderbook_schema)
        orderbook.update_orderbook(data)

@app.timer(interval=10)
async def print_orderbook():
    orderbook.get_orderbook()



if __name__ == '__main__':
    logging.warning('starting service')
    time.sleep(30)
    app.main()