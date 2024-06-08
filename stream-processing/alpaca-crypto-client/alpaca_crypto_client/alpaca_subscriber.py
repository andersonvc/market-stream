from typing import Dict

from alpaca.data.live.crypto import CryptoDataStream
from alpaca.data.models import Orderbook


class CustomOrderbook(Orderbook):
    """
    Custom Orderbook class to detect when initializing a full orderbook (is_full=True) or appending an existing one.
    Matches default Orderbook class is all other aspects.
    """

    is_full: bool = False

    def __init__(self, symbol, raw_data=False, is_full=False):
        super().__init__(symbol, raw_data)
        self.is_full = is_full


class L2CryptoDataStream(CryptoDataStream):
    """
    Subscribes to Alpaca live crypto websocket feed and dispatches messages to registered handlers.
    """

    def __init__(self, api_key, secret_key, raw_data=False):
        super().__init__(api_key=api_key, secret_key=secret_key)
        self._handlers["orderbooks"] = {}
        self._raw_data = raw_data

    def subscribe_orderbook(self, handler, *symbols):
        self._subscribe(handler, symbols, self._handlers["orderbooks"])

    def _orderbook_cast(self, msg: Dict) -> Dict:
        """Casts orderbook message to correct format"""
        result = msg
        if not self._raw_data:
            msg["t"] = msg["t"].to_datetime()
            result = CustomOrderbook(msg["S"], msg, is_full=msg["r"])
        return result

    async def _dispatch(self, msg) -> None:
        """
        Overrides the CryptoDataStream dispatch method to handle orderbook messages.
        """
        msg_type = msg.get("T")
        symbol = msg.get("S")
        if msg_type == "o":
            handler = self._handlers["orderbooks"].get(
                symbol, self._handlers["orderbooks"].get("*", None)
            )
            if handler:
                await handler(self._orderbook_cast(msg))
