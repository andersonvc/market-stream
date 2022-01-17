import aiohttp
import asyncio
from collections import deque
import datetime
from functools import wraps
import json
import logging
import os
import sys

import dotenv
import psycopg2
import psycopg2.extras

dotenv.load_dotenv("../secrets/alpaca.env")


async def alpaca_auth(ws):
    alpaca_id = os.getenv('ALPACA_API_ID')
    alpaca_secret = os.getenv('ALPACA_API_KEY')
    
    auth_message = json.dumps({
        'action':'auth',
        'key':alpaca_id,
        'secret':alpaca_secret,
    })

    await ws.send_str(auth_message)

    async for msg in ws:
        if msg.type == aiohttp.WSMsgType.TEXT:
            msg = json.loads(msg.data)[0]
            expected_msg = {'T': 'success', 'msg': 'authenticated'}
            if msg == expected_msg:
                break
            else:
                raise Exception(f'Unexpected auth response: {msg}')
        else:
            raise Exception(f'Auth Error: {msg.data}')

    logging.info('Authentication successful')


def alpaca_connection_wrapper(func):
    
    @wraps(func)
    async def _impl(self,*args,**kwargs):

        while True:
            try:
                websocket_uri = self.alpaca_uri
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(websocket_uri) as ws:

                        # Initial handshake
                        rec_msg = await ws.receive()
                        logging.debug(rec_msg)
                        if rec_msg.type==aiohttp.WSMsgType.TEXT:
                            rec_msg = json.loads(rec_msg.data)[0]
                            expected_msg = {"T":"success","msg":"connected"}
                            if rec_msg != expected_msg:
                                raise Exception(f'Server initial msg doesnt match expected:\n{rec_msg}!={expected_msg}')
                        else:
                            raise Exception(f'Initial server message type not expected: {rec_msg.type}')
                        logging.info('Server connection successful')

                        # Authentication
                        await alpaca_auth(ws)
                        
                        # Launch Function
                        await func(self,ws=ws)

            except Exception as e:
                logging.error(f'Alpaca connection failure: {e}')
    
    return _impl


class AlpacaClient():

    trade_recs = deque([])
    CRYPTO_TRADE_COLUMNS = '(id,ts,instrument,exchange,price,trade_size,taker_side)'
    EQUITY_TRADE_COLUMNS = '(id,ts,symbol,exchange,price,trade_size,'

    def __init__(self, is_crypto=False, alpaca_uri='wss://stream.data.alpaca.markets/v1beta1/crypto', timescaledb_uri='192.168.1.13', timescaledb_port='5432', logging_level = logging.DEBUG):

        dbuser = os.getenv('DBUSER')
        dbpass = os.getenv('DBPASS')
        dbname = os.getenv('DBNAME')
        dburl = timescaledb_uri
        dbport = timescaledb_port
        self.database_connection = f"postgres://{dbuser}:{dbpass}@{dburl}:{dbport}/{dbname}"
        
        self.is_crypto=is_crypto
        if self.is_crypto:

            self.table_name = 'crypto_trades'
            self.table_columns = '(id,ts,instrument,exchange,price,trade_size,taker_side)'
            self.alpaca_uri = 'wss://stream.data.alpaca.markets/v1beta1/crypto'
            self.message_parser = lambda x: [int(x['i']),x['t'],x['S'],x['x'],x['p'],x['s'],x['tks'],]
        
        else:
            self.table_name = 'equity_trades'
            self.table_columns = '(id,ts,instrument,exchange,price,trade_size,trade_cond,tape)'
            self.alpaca_uri = 'wss://stream.data.alpaca.markets/v2/iex'
            self.message_parser = lambda x: [int(x['i']),x['t'],x['S'],x['x'],x['p'],x['s'],''.join(x['c']),x['z']]        
        
        self.db_write_delay = 0.05

        self.trades = []
        self.quotes = []
        self.bars = []

        logging.basicConfig(level=logging_level)

    def reset_database(self):
        """
        Delete database records, all tables, & rebuild database
        """
        
        with psycopg2.connect(self.database_connection) as conn:
            cursor = conn.cursor()
            cursor.execute("ROLLBACK")

            try:
                cursor.execute("DROP TABLE crypto_trades")
            except:
                pass

            try:
                cursor.execute("DROP TABLE equity_trades")
            except:
                pass

            try:
                create_table = (
                    """
                    CREATE TABLE crypto_trades (
                        id BIGINT,
                        ts TIMESTAMP,
                        instrument VARCHAR(9),
                        exchange VARCHAR(6),
                        price DOUBLE PRECISION,
                        trade_size DOUBLE PRECISION,
                        taker_side CHAR,
                        PRIMARY KEY (id,ts));
                    """
                )
                cursor.execute(create_table);
                cursor.execute("SELECT create_hypertable('crypto_trades', 'ts');")
                
            except:
                raise Exception('Failed to create crypto_trades database table.')
            
            try:
                create_table = (
                    """
                    CREATE TABLE equity_trades (
                        id BIGINT,
                        ts TIMESTAMP,
                        instrument VARCHAR(9),
                        exchange VARCHAR(6),
                        price DOUBLE PRECISION,
                        trade_size DOUBLE PRECISION,
                        trade_cond VARCHAR(4),
                        tape CHAR,
                        PRIMARY KEY (id,ts));
                    """
                )
                cursor.execute(create_table);
                cursor.execute("SELECT create_hypertable('equity_trades', 'ts');")
                
            except:
                raise Exception('Failed to create equity_trades database table.')

    @alpaca_connection_wrapper
    async def _stream_listener(self,ws):
        """
        Alpaca async websocket listener
        """
        listener_message = json.dumps({
            'action':'subscribe',
            'trades':self.trades,
            'quotes':self.quotes,
            'bars':self.bars,
        })

        await ws.send_str(listener_message)

        async for msg in ws:
            if msg.type==aiohttp.WSMsgType.TEXT:                
                data = json.loads(msg.data)
                logging.error(data)
                for rec in data:
                    logging.debug(rec)
                    if rec['T']=='t':
                        new_rec = self.message_parser(rec)
                        self.trade_recs.appendleft(new_rec)
                        logging.debug(new_rec)
                    else: #if rec['T']=='error':
                        logging.debug(f'alpaca error: {rec}')
            elif msg.type==aiohttp.WSMsgType.ERROR:
                logging.error(msg.data)
    
    async def _database_writer(self):
        """
        Async publish alpaca records to timescaleDB
        """

        query = f"INSERT INTO {self.table_name} {self.table_columns} VALUES %s"

        curr_records = []
        while True:
            try:
                with psycopg2.connect(self.database_connection) as conn:
                    cursor = conn.cursor()
                    while True:
                        if self.trade_recs:
                            curr_records = [self.trade_recs.pop() for _ in range(len(self.trade_recs))]

                            psycopg2.extras.execute_values(
                                cursor, 
                                query, 
                                curr_records, 
                                template=None,
                            )

                            conn.commit()
                        else:
                            await asyncio.sleep(self.db_write_delay)
            except Exception as e:
                logging.error(f'TimescaleDB connection error: {e}')
                logging.error(f'The following records are in limbo...')
                for entry in curr_records:
                    logging.error(entry)
                await asyncio.sleep(1)
    
    async def run_collector(self):
        await asyncio.gather(
            self._stream_listener(),
            self._database_writer(),
    )

def start_crypto_client():
    client = AlpacaClient(logging_level=logging.ERROR,is_crypto=True)
    client.trades=['BTCUSD','ETHUSD','LTCUSD']
    asyncio.run(client.run_collector())

def start_equity_client():
    client = AlpacaClient(logging_level=logging.ERROR,is_crypto=False)
    client.trades=['AAPL','META','TSLA']
    asyncio.run(client.run_collector())

def reset_database():
    client = AlpacaClient()
    client.reset_database()


if __name__ == "__main__":
    globals()[sys.argv[1]]()
