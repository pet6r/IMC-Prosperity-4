"""
Tutorial Round 1 — dual-product market making (Emeralds, Tomatoes).

Uses book mid for fair value (with an Emerald anchor band), inventory skew, optional
extra ticks toward flattening, and optional aggressive crossing only in the flattening
direction. Includes the Prosperity `Logger` helper for compressed JSON logs.
"""

import json
import math
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
    """Builds a JSON log line for the backtester; truncates fields to stay under size limits."""

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
        return [[listing.symbol, listing.product, listing.denomination] for listing in listings.values()]

    def compress_order_depths(self, order_depths: dict[Symbol, OrderDepth]) -> dict[Symbol, list[Any]]:
        return {symbol: [depth.buy_orders, depth.sell_orders] for symbol, depth in order_depths.items()}

    def compress_trades(self, trades: dict[Symbol, list[Trade]]) -> list[list[Any]]:
        compressed: list[list[Any]] = []
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
        compressed: list[list[Any]] = []
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

# --- Strategy parameters ---------------------------------------------------------

LIMITS: dict[str, int] = {
    "EMERALDS": 20,
    "TOMATOES": 20,
}

EMERALD_ANCHOR = 10_000.0
EMERALD_BAND = 5.0
TOMATO_FALLBACK_MID = 5000.0

# At |position| == limit, fair shifts by ±this many price units (short -> +skew).
INVENTORY_SKEW_MAX = 2

# Extra integer ticks on bid/ask bounds toward flattening (scaled by |position|/limit). 0 disables.
POSITION_REDUCE_AT_FAIR_MAX_TICKS = 1.0

# Wide Tomatoes books: quote slightly less aggressive to preserve edge.
TOMATO_WIDE_SPREAD_MIN = 13
TOMATO_WIDE_SPREAD_EXTRA_EDGE = 1

# If True: only lift asks when not long, only hit bids when not short (passive quotes unchanged).
AGGRESSIVE_CROSS_FLATTEN_ONLY = True


def _best_bid_ask(depth: OrderDepth | None) -> tuple[int, int] | None:
    """Best bid (highest) and best ask (lowest), or None if book incomplete."""
    if not depth or not depth.buy_orders or not depth.sell_orders:
        return None
    return max(depth.buy_orders.keys()), min(depth.sell_orders.keys())


def _mid_price(state: TradingState, symbol: str) -> float | None:
    """Mid price (bb + ba) / 2."""
    ba = _best_bid_ask(state.order_depths.get(symbol))
    if ba is None:
        return None
    best_bid, best_ask = ba
    return (best_bid + best_ask) / 2.0


def _fair_emeralds(state: TradingState) -> float:
    """Anchor mid near 10_000 inside a band; otherwise track book mid."""
    mid = _mid_price(state, "EMERALDS")
    if mid is None:
        return EMERALD_ANCHOR
    if (EMERALD_ANCHOR - EMERALD_BAND) <= mid <= (EMERALD_ANCHOR + EMERALD_BAND):
        return EMERALD_ANCHOR
    return mid


def _fair_tomatoes(state: TradingState) -> float:
    mid = _mid_price(state, "TOMATOES")
    return mid if mid is not None else TOMATO_FALLBACK_MID


def _inventory_skewed_fair(fair: float, position: int, limit: int) -> float:
    """Shift effective fair toward flattening: short -> raise fair, long -> lower fair."""
    if limit <= 0:
        return fair
    skew = -INVENTORY_SKEW_MAX * (position / limit)
    return fair + skew


def _quote_bounds_around_fair(fair: float) -> tuple[int, int]:
    """Integer max buy and min sell bracketing fair on the tick grid."""
    if fair % 1 == 0:
        iv = int(fair)
        return iv - 1, iv + 1
    return math.floor(fair), math.ceil(fair)


def _position_reduce_ticks(max_buy: int, min_sell: int, position: int, limit: int) -> tuple[int, int]:
    """Move both bounds toward inventory reduction (after fair + inventory skew)."""
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


def _market_make(symbol: str, state: TradingState, fair: float) -> list[Order]:
    """One bid and one ask per tick: sweep through book where price allows, then join/improve."""
    depth = state.order_depths.get(symbol)
    ba = _best_bid_ask(depth)
    if ba is None:
        return []

    limit = LIMITS.get(symbol, 20)
    position = state.position.get(symbol, 0)
    to_buy = limit - position
    to_sell = limit + position

    fair = _inventory_skewed_fair(fair, position, limit)

    best_bid, best_ask = ba
    spread = best_ask - best_bid
    buy_orders = sorted(depth.buy_orders.items(), reverse=True)
    sell_orders = sorted(depth.sell_orders.items())

    max_buy_price, min_sell_price = _quote_bounds_around_fair(fair)
    max_buy_price, min_sell_price = _position_reduce_ticks(max_buy_price, min_sell_price, position, limit)
    if symbol == "TOMATOES" and spread >= TOMATO_WIDE_SPREAD_MIN:
        max_buy_price -= TOMATO_WIDE_SPREAD_EXTRA_EDGE
        min_sell_price += TOMATO_WIDE_SPREAD_EXTRA_EDGE

    # Long: do not lift asks; short: do not hit bids (when flatten-only crossing is on).
    use_flatten_cross = AGGRESSIVE_CROSS_FLATTEN_ONLY
    allow_lift_asks = not use_flatten_cross or position <= 0
    allow_hit_bids = not use_flatten_cross or position >= 0

    orders: list[Order] = []

    if allow_lift_asks:
        for price, volume in sell_orders:
            if to_buy > 0 and price <= max_buy_price:
                q = min(to_buy, -volume)
                orders.append(Order(symbol, price, q))
                to_buy -= q

    if to_buy > 0:
        price = next((p + 1 for p, _ in buy_orders if p < max_buy_price), max_buy_price)
        orders.append(Order(symbol, price, to_buy))

    if allow_hit_bids:
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
    """Prosperity tutorial trader: quotes EMERALDS and TOMATOES from fair + inventory logic."""

    def bid(self) -> int:
        """Competition hook (unused in this round’s logic)."""
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
