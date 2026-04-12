"""
Tutorial Round 1 — market making + Logger
"""

import json
from typing import Any

from datamodel import (
    Listing,
    Observation,
    Order,
    OrderDepth,
    ProsperityEncoder,
    Symbol,
    Trade,
    TradingState,
)


class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(
        self,
        state: TradingState,
        orders: dict[Symbol, list[Order]],
        conversions: int,
        trader_data: str,
    ) -> None:
        base_length = len(
            self.to_json(
                [
                    self.compress_state(state, ""),
                    self.compress_orders(orders),
                    conversions,
                    "",
                    "",
                ]
            )
        )
        max_item_length = (self.max_log_length - base_length) // 3

        print(
            self.to_json(
                [
                    self.compress_state(state, self.truncate(state.traderData, max_item_length)),
                    self.compress_orders(orders),
                    conversions,
                    self.truncate(trader_data, max_item_length),
                    self.truncate(self.logs, max_item_length),
                ]
            )
        )

        self.logs = ""

    def compress_state(self, state: TradingState, trader_data: str) -> list[Any]:
        return [
            state.timestamp,
            trader_data,
            self.compress_listings(state.listings),
            self.compress_order_depths(state.order_depths),
            self.compress_trades(state.own_trades),
            self.compress_trades(state.market_trades),
            state.position,
            self.compress_observations(state.observations),
        ]

    def compress_listings(self, listings: dict[Symbol, Listing]) -> list[list[Any]]:
        compressed = []
        for listing in listings.values():
            compressed.append([listing.symbol, listing.product, listing.denomination])
        return compressed

    def compress_order_depths(self, order_depths: dict[Symbol, OrderDepth]) -> dict[Symbol, list[Any]]:
        compressed = {}
        for symbol, order_depth in order_depths.items():
            compressed[symbol] = [order_depth.buy_orders, order_depth.sell_orders]
        return compressed

    def compress_trades(self, trades: dict[Symbol, list[Trade]]) -> list[list[Any]]:
        compressed = []
        for arr in trades.values():
            for trade in arr:
                compressed.append(
                    [
                        trade.symbol,
                        trade.price,
                        trade.quantity,
                        trade.buyer,
                        trade.seller,
                        trade.timestamp,
                    ]
                )
        return compressed

    def compress_observations(self, observations: Observation) -> list[Any]:
        conversion_observations = {}
        for product, observation in observations.conversionObservations.items():
            conversion_observations[product] = [
                observation.bidPrice,
                observation.askPrice,
                observation.transportFees,
                observation.exportTariff,
                observation.importTariff,
                observation.sugarPrice,
                observation.sunlightIndex,
            ]
        return [observations.plainValueObservations, conversion_observations]

    def compress_orders(self, orders: dict[Symbol, list[Order]]) -> list[list[Any]]:
        compressed = []
        for arr in orders.values():
            for order in arr:
                compressed.append([order.symbol, order.price, order.quantity])
        return compressed

    def to_json(self, value: Any) -> str:
        return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

    def truncate(self, value: str, max_length: int) -> str:
        lo, hi = 0, min(len(value), max_length)
        out = ""

        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = value[:mid]
            if len(candidate) < len(value):
                candidate += "..."
            encoded_candidate = json.dumps(candidate)
            if len(encoded_candidate) <= max_length:
                out = candidate
                lo = mid + 1
            else:
                hi = mid - 1

        return out


logger = Logger()


LIMITS: dict[str, int] = {
    "EMERALDS": 20,
    "TOMATOES": 20,
}

EMERALD_ANCHOR = 10_000.0
EMERALD_BAND = 5.0

# At |position| == limit, fair is shifted by ±this many price units (short -> +skew -> buy higher / sell higher).
INVENTORY_SKEW_MAX = 2

# Extra integer ticks on both bid/ask bounds toward flattening, scaled by |position|/limit.
# Applied *after* skewed fair → max_buy/min_sell. Short -> raise both (more aggressive buys, less aggressive sells).
# 0 disables. Tune 1–2; too high narrows effective spread vs adversaries.
POSITION_REDUCE_AT_FAIR_MAX_TICKS = 1.0

# On very wide TOMATOES books (often 13-14), quote a bit less aggressively to keep more edge.
TOMATO_WIDE_SPREAD_MIN = 13
TOMATO_WIDE_SPREAD_EXTRA_EDGE = 1


def _floori(x: float) -> int:
    i = int(x)
    return i if x >= i else i - 1


def _ceili(x: float) -> int:
    i = int(x)
    return i if x <= i else i + 1


def _mid_price(state: TradingState, symbol: str) -> float | None:
    """Mid from best bid (highest) and best ask (lowest), i.e. (bb + ba) / 2."""
    depth = state.order_depths.get(symbol)
    if not depth or not depth.buy_orders or not depth.sell_orders:
        return None
    best_bid = max(depth.buy_orders.keys())
    best_ask = min(depth.sell_orders.keys())
    return (best_bid + best_ask) / 2.0


def _fair_emeralds(state: TradingState) -> float:
    mid = _mid_price(state, "EMERALDS")
    if mid is None:
        return EMERALD_ANCHOR
    if (EMERALD_ANCHOR - EMERALD_BAND) <= mid <= (EMERALD_ANCHOR + EMERALD_BAND):
        return EMERALD_ANCHOR
    return mid


def _fair_tomatoes(state: TradingState) -> float:
    mid = _mid_price(state, "TOMATOES")
    return mid if mid is not None else 5000.0


def _inventory_skewed_true(true_value: float, position: int, limit: int) -> float:
    """Move effective fair toward flattening: short -> raise fair; long -> lower fair."""
    if limit <= 0:
        return true_value
    skew = -INVENTORY_SKEW_MAX * (position / limit)
    return true_value + skew


def _position_reduce_ticks(max_buy: int, min_sell: int, position: int, limit: int) -> tuple[int, int]:
    """Shift both bounds toward inventory reduction (on top of fair + inventory skew)."""
    if limit <= 0 or POSITION_REDUCE_AT_FAIR_MAX_TICKS <= 0:
        return max_buy, min_sell
    scale = abs(position) / float(limit)
    delta = int(round(POSITION_REDUCE_AT_FAIR_MAX_TICKS * scale))
    if delta == 0:
        return max_buy, min_sell
    if position < 0:
        return max_buy + delta, min_sell + delta
    if position > 0:
        return max_buy - delta, min_sell - delta
    return max_buy, min_sell


def _market_make(symbol: str, state: TradingState, true_value: float) -> list[Order]:
    depth = state.order_depths.get(symbol)
    if not depth or not depth.buy_orders or not depth.sell_orders:
        return []

    limit = LIMITS.get(symbol, 20)
    position = state.position.get(symbol, 0)
    to_buy = limit - position
    to_sell = limit + position

    true_value = _inventory_skewed_true(true_value, position, limit)

    buy_orders = sorted(depth.buy_orders.items(), reverse=True)
    sell_orders = sorted(depth.sell_orders.items())
    best_bid = buy_orders[0][0]
    best_ask = sell_orders[0][0]
    spread = best_ask - best_bid

    max_buy_price = int(true_value) - 1 if true_value % 1 == 0 else _floori(true_value)
    min_sell_price = int(true_value) + 1 if true_value % 1 == 0 else _ceili(true_value)

    max_buy_price, min_sell_price = _position_reduce_ticks(max_buy_price, min_sell_price, position, limit)
    if symbol == "TOMATOES" and spread >= TOMATO_WIDE_SPREAD_MIN:
        max_buy_price -= TOMATO_WIDE_SPREAD_EXTRA_EDGE
        min_sell_price += TOMATO_WIDE_SPREAD_EXTRA_EDGE

    orders: list[Order] = []

    for price, volume in sell_orders:
        if to_buy > 0 and price <= max_buy_price:
            q = min(to_buy, -volume)
            orders.append(Order(symbol, price, q))
            to_buy -= q

    if to_buy > 0:
        price = next((p + 1 for p, _ in buy_orders if p < max_buy_price), max_buy_price)
        orders.append(Order(symbol, price, to_buy))

    for price, volume in buy_orders:
        if to_sell > 0 and price >= min_sell_price:
            q = min(to_sell, volume)
            orders.append(Order(symbol, price, -q))
            to_sell -= q

    if to_sell > 0:
        price = next((p - 1 for p, _ in sell_orders if p > min_sell_price), min_sell_price)
        orders.append(Order(symbol, price, -to_sell))

    return orders


class Trader:
    def bid(self) -> int:
        return 15

    def run(self, state: TradingState):
        orders: dict[str, list[Order]] = {}
        conversions = 0

        if "EMERALDS" in state.order_depths:
            orders["EMERALDS"] = _market_make("EMERALDS", state, _fair_emeralds(state))

        if "TOMATOES" in state.order_depths:
            orders["TOMATOES"] = _market_make("TOMATOES", state, _fair_tomatoes(state))

        trader_data = ""
        logger.flush(state, orders, conversions, trader_data)
        return orders, conversions, trader_data