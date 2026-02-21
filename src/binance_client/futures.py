"""Binance USDT-M Futures data client for analysis.

Provides methods to fetch historical market data from the Binance Futures API.
All data-fetching methods return pandas DataFrames with typed columns.
Large date ranges are automatically paginated.

Supported data types:
    - OHLCV klines (candlestick)
    - Index price klines (spot weighted average)
    - Mark price klines (fair price for PnL/liquidation)
    - Funding rate history
    - Open interest history
    - Long/short account ratio (global)
    - Top trader long/short ratio (by accounts & positions)
    - Taker buy/sell volume ratio
    - Aggregated trades
    - Exchange info, premium index, 24hr ticker

Usage:
    from binance_client import BinanceFuturesClient

    client = BinanceFuturesClient()
    df = client.get_klines("BTCUSDT", "1h", "2025-01-01", "2025-02-01")
"""

import logging

import pandas as pd

from .base import BinanceBaseClient, to_milliseconds

logger = logging.getLogger(__name__)

# Valid intervals for kline endpoints
KLINE_INTERVALS = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
}

# Valid periods for analytics endpoints (OI, LS ratio, taker volume)
ANALYTICS_PERIODS = {"5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"}


class BinanceFuturesClient(BinanceBaseClient):
    """Client for Binance USDT-M Futures historical data.

    All data-fetching methods return pandas DataFrames with typed columns.
    Large date ranges are automatically paginated.
    """

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _fetch_klines_raw(
        self,
        endpoint: str,
        params_base: dict,
        start_ms: int,
        end_ms: int,
        limit: int,
    ) -> list[list]:
        """Paginated fetch for kline-format endpoints."""
        all_data: list[list] = []
        current = start_ms

        while current < end_ms:
            params = {
                **params_base,
                "startTime": current,
                "endTime": end_ms,
                "limit": limit,
            }
            data = self._request(f"{self.FUTURES_BASE_URL}{endpoint}", params)
            if not data:
                break

            all_data.extend(data)
            logger.info(
                "Fetched %d candles (total: %d)", len(data), len(all_data)
            )

            if len(data) < limit:
                break
            # close_time is at index 6; advance past it
            current = data[-1][6] + 1

        return all_data

    def _fetch_records_raw(
        self,
        endpoint: str,
        params_base: dict,
        start_ms: int,
        end_ms: int,
        limit: int,
        time_field: str = "timestamp",
    ) -> list[dict]:
        """Paginated fetch for JSON-record endpoints (funding rate, OI, ratios)."""
        all_data: list[dict] = []
        current = start_ms

        while current < end_ms:
            params = {
                **params_base,
                "startTime": current,
                "endTime": end_ms,
                "limit": limit,
            }
            data = self._request(f"{self.FUTURES_BASE_URL}{endpoint}", params)
            if not data:
                break

            all_data.extend(data)
            logger.info(
                "Fetched %d records (total: %d)", len(data), len(all_data)
            )

            if len(data) < limit:
                break
            current = int(data[-1][time_field]) + 1

        return all_data

    @staticmethod
    def _klines_to_df(raw: list[list], include_extra: bool = True) -> pd.DataFrame:
        """Convert raw kline arrays to DataFrame.

        Args:
            raw: Raw kline data from Binance API.
            include_extra: If True, include volume breakdown columns.
                Set to False for index/mark price klines where those are always 0.
        """
        if not raw:
            return pd.DataFrame()

        columns = [
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_volume", "taker_buy_quote_volume", "_ignore",
        ]
        df = pd.DataFrame(raw, columns=columns).drop(columns=["_ignore"])

        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)

        float_cols = [
            "open", "high", "low", "close", "volume",
            "quote_volume", "taker_buy_volume", "taker_buy_quote_volume",
        ]
        for col in float_cols:
            df[col] = df[col].astype(float)
        df["trades"] = df["trades"].astype(int)

        if not include_extra:
            df = df[["timestamp", "open", "high", "low", "close"]]

        return df

    # ------------------------------------------------------------------ #
    #  OHLCV Klines                                                        #
    # ------------------------------------------------------------------ #

    def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time,
        end_time,
        limit: int = 1500,
    ) -> pd.DataFrame:
        """Fetch OHLCV candlestick data.

        Args:
            symbol: Trading pair (e.g. 'BTCUSDT')
            interval: Kline interval (1m,3m,5m,15m,30m,1h,2h,4h,6h,8h,12h,1d,3d,1w,1M)
            start_time: Start time (datetime, 'YYYY-MM-DD', or ms timestamp)
            end_time: End time
            limit: Max candles per request (max 1500)

        Returns:
            DataFrame: timestamp, open, high, low, close, volume, close_time,
                       quote_volume, trades, taker_buy_volume, taker_buy_quote_volume
        """
        raw = self._fetch_klines_raw(
            "/fapi/v1/klines",
            {"symbol": symbol, "interval": interval},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
            limit,
        )
        logger.info("[%s] Total klines fetched: %d", symbol, len(raw))
        return self._klines_to_df(raw)

    # ------------------------------------------------------------------ #
    #  Index Price Klines                                                   #
    # ------------------------------------------------------------------ #

    def get_index_price_klines(
        self,
        pair: str,
        interval: str,
        start_time,
        end_time,
        limit: int = 1500,
    ) -> pd.DataFrame:
        """Fetch index price klines (weighted average from spot exchanges).

        The index price represents the fair spot price aggregated across
        multiple exchanges. Useful for basis/premium analysis.

        Args:
            pair: Trading pair (e.g. 'BTCUSDT')
            interval: Kline interval
            start_time: Start time
            end_time: End time

        Returns:
            DataFrame: timestamp, open, high, low, close
        """
        raw = self._fetch_klines_raw(
            "/fapi/v1/indexPriceKlines",
            {"pair": pair, "interval": interval},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
            limit,
        )
        logger.info("[%s] Total index price klines fetched: %d", pair, len(raw))
        return self._klines_to_df(raw, include_extra=False)

    # ------------------------------------------------------------------ #
    #  Mark Price Klines                                                    #
    # ------------------------------------------------------------------ #

    def get_mark_price_klines(
        self,
        symbol: str,
        interval: str,
        start_time,
        end_time,
        limit: int = 1500,
    ) -> pd.DataFrame:
        """Fetch mark price klines.

        The mark price is used for PnL calculation and liquidation.
        It incorporates funding rate and index price to prevent manipulation.

        Returns:
            DataFrame: timestamp, open, high, low, close
        """
        raw = self._fetch_klines_raw(
            "/fapi/v1/markPriceKlines",
            {"symbol": symbol, "interval": interval},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
            limit,
        )
        logger.info("[%s] Total mark price klines fetched: %d", symbol, len(raw))
        return self._klines_to_df(raw, include_extra=False)

    # ------------------------------------------------------------------ #
    #  Funding Rate History                                                 #
    # ------------------------------------------------------------------ #

    def get_funding_rate_history(
        self,
        symbol: str,
        start_time,
        end_time,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """Fetch funding rate history.

        Funding is exchanged between longs and shorts every 8 hours.
        Positive rate = longs pay shorts, negative = shorts pay longs.

        Returns:
            DataFrame: timestamp, symbol, funding_rate, mark_price
        """
        raw = self._fetch_records_raw(
            "/fapi/v1/fundingRate",
            {"symbol": symbol},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
            limit,
            time_field="fundingTime",
        )
        logger.info("[%s] Total funding rate records: %d", symbol, len(raw))

        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw)
        df = df.rename(columns={
            "fundingTime": "timestamp",
            "fundingRate": "funding_rate",
            "markPrice": "mark_price",
        })
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["funding_rate"] = df["funding_rate"].astype(float)
        df["mark_price"] = df["mark_price"].astype(float)
        return df[["timestamp", "symbol", "funding_rate", "mark_price"]]

    # ------------------------------------------------------------------ #
    #  Open Interest History                                                #
    # ------------------------------------------------------------------ #

    def get_open_interest_history(
        self,
        symbol: str,
        period: str,
        start_time,
        end_time,
        limit: int = 500,
    ) -> pd.DataFrame:
        """Fetch open interest history.

        Args:
            period: Aggregation period (5m,15m,30m,1h,2h,4h,6h,12h,1d)

        Note:
            Only data from the last 30 days is available from Binance.

        Returns:
            DataFrame: timestamp, symbol, open_interest, open_interest_value
        """
        raw = self._fetch_records_raw(
            "/futures/data/openInterestHist",
            {"symbol": symbol, "period": period},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
            limit,
        )
        logger.info("[%s] Total OI history records: %d", symbol, len(raw))

        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw)
        df = df.rename(columns={
            "sumOpenInterest": "open_interest",
            "sumOpenInterestValue": "open_interest_value",
        })
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["open_interest"] = df["open_interest"].astype(float)
        df["open_interest_value"] = df["open_interest_value"].astype(float)
        return df[["timestamp", "symbol", "open_interest", "open_interest_value"]]

    # ------------------------------------------------------------------ #
    #  Global Long/Short Account Ratio                                      #
    # ------------------------------------------------------------------ #

    def get_long_short_ratio(
        self,
        symbol: str,
        period: str,
        start_time,
        end_time,
        limit: int = 500,
    ) -> pd.DataFrame:
        """Fetch global long/short account ratio.

        Shows the ratio of accounts holding long vs short positions
        across all Binance Futures users.

        Args:
            period: Aggregation period (5m,15m,30m,1h,2h,4h,6h,12h,1d)

        Note:
            Only data from the last 30 days is available.

        Returns:
            DataFrame: timestamp, symbol, long_short_ratio, long_account, short_account
        """
        raw = self._fetch_records_raw(
            "/futures/data/globalLongShortAccountRatio",
            {"symbol": symbol, "period": period},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
            limit,
        )
        logger.info("[%s] Total LS ratio records: %d", symbol, len(raw))

        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw)
        df = df.rename(columns={
            "longShortRatio": "long_short_ratio",
            "longAccount": "long_account",
            "shortAccount": "short_account",
        })
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        for col in ["long_short_ratio", "long_account", "short_account"]:
            df[col] = df[col].astype(float)
        return df[["timestamp", "symbol", "long_short_ratio", "long_account", "short_account"]]

    # ------------------------------------------------------------------ #
    #  Top Trader Long/Short Ratio (Accounts)                               #
    # ------------------------------------------------------------------ #

    def get_top_trader_long_short_ratio_accounts(
        self,
        symbol: str,
        period: str,
        start_time,
        end_time,
        limit: int = 500,
    ) -> pd.DataFrame:
        """Fetch top trader long/short ratio by number of accounts.

        Measures the proportion of top traders (by margin balance)
        holding long vs short positions, counted by account.

        Note:
            Only data from the last 30 days is available.

        Returns:
            DataFrame: timestamp, symbol, long_short_ratio, long_account, short_account
        """
        raw = self._fetch_records_raw(
            "/futures/data/topLongShortAccountRatio",
            {"symbol": symbol, "period": period},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
            limit,
        )
        logger.info("[%s] Total top trader LS (accounts) records: %d", symbol, len(raw))

        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw)
        df = df.rename(columns={
            "longShortRatio": "long_short_ratio",
            "longAccount": "long_account",
            "shortAccount": "short_account",
        })
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        for col in ["long_short_ratio", "long_account", "short_account"]:
            df[col] = df[col].astype(float)
        return df[["timestamp", "symbol", "long_short_ratio", "long_account", "short_account"]]

    # ------------------------------------------------------------------ #
    #  Top Trader Long/Short Ratio (Positions)                              #
    # ------------------------------------------------------------------ #

    def get_top_trader_long_short_ratio_positions(
        self,
        symbol: str,
        period: str,
        start_time,
        end_time,
        limit: int = 500,
    ) -> pd.DataFrame:
        """Fetch top trader long/short ratio by position size.

        Measures the proportion of top traders (by margin balance)
        holding long vs short positions, weighted by position size.

        Note:
            Only data from the last 30 days is available.

        Returns:
            DataFrame: timestamp, symbol, long_short_ratio, long_account, short_account
        """
        raw = self._fetch_records_raw(
            "/futures/data/topLongShortPositionRatio",
            {"symbol": symbol, "period": period},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
            limit,
        )
        logger.info("[%s] Total top trader LS (positions) records: %d", symbol, len(raw))

        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw)
        df = df.rename(columns={
            "longShortRatio": "long_short_ratio",
            "longAccount": "long_account",
            "shortAccount": "short_account",
        })
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        for col in ["long_short_ratio", "long_account", "short_account"]:
            df[col] = df[col].astype(float)
        return df[["timestamp", "symbol", "long_short_ratio", "long_account", "short_account"]]

    # ------------------------------------------------------------------ #
    #  Taker Buy/Sell Volume Ratio                                          #
    # ------------------------------------------------------------------ #

    def get_taker_buy_sell_ratio(
        self,
        symbol: str,
        period: str,
        start_time,
        end_time,
        limit: int = 500,
    ) -> pd.DataFrame:
        """Fetch taker buy/sell volume ratio.

        Shows the ratio of aggressive buying vs selling volume.
        Values > 1 indicate more taker buying (bullish pressure).

        Args:
            period: Aggregation period (5m,15m,30m,1h,2h,4h,6h,12h,1d)

        Note:
            Only data from the last 30 days is available.

        Returns:
            DataFrame: timestamp, buy_sell_ratio, buy_vol, sell_vol
        """
        raw = self._fetch_records_raw(
            "/futures/data/takerlongshortRatio",
            {"symbol": symbol, "period": period},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
            limit,
        )
        logger.info("[%s] Total taker buy/sell records: %d", symbol, len(raw))

        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw)
        df = df.rename(columns={
            "buySellRatio": "buy_sell_ratio",
            "buyVol": "buy_vol",
            "sellVol": "sell_vol",
        })
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        for col in ["buy_sell_ratio", "buy_vol", "sell_vol"]:
            df[col] = df[col].astype(float)
        return df[["timestamp", "buy_sell_ratio", "buy_vol", "sell_vol"]]

    # ------------------------------------------------------------------ #
    #  Aggregated Trades                                                    #
    # ------------------------------------------------------------------ #

    def get_agg_trades(
        self,
        symbol: str,
        start_time,
        end_time,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """Fetch aggregated trade data.

        Binance limits time windows to 1 hour per request for this endpoint.
        This method automatically chunks larger ranges into 1-hour windows
        and paginates within each window if needed.

        Warning:
            Large date ranges produce very large datasets.
            Consider using short time windows for analysis.

        Returns:
            DataFrame: timestamp, agg_trade_id, price, quantity,
                       first_trade_id, last_trade_id, is_buyer_maker
        """
        url = f"{self.FUTURES_BASE_URL}/fapi/v1/aggTrades"
        start_ms = to_milliseconds(start_time)
        end_ms = to_milliseconds(end_time)
        HOUR_MS = 3_600_000

        all_data: list[dict] = []
        chunk_start = start_ms

        while chunk_start < end_ms:
            chunk_end = min(chunk_start + HOUR_MS, end_ms)

            # Initial request with time window (max 1 hour)
            params = {
                "symbol": symbol,
                "startTime": chunk_start,
                "endTime": chunk_end,
                "limit": limit,
            }
            batch = self._request(url, params)
            if not batch:
                chunk_start = chunk_end
                continue

            all_data.extend(batch)

            # If we hit the limit, paginate by fromId within this hour
            while len(batch) >= limit:
                params = {
                    "symbol": symbol,
                    "fromId": batch[-1]["a"] + 1,
                    "limit": limit,
                }
                batch = self._request(url, params)
                if not batch or batch[0]["T"] > chunk_end:
                    break
                # Keep only trades within our time window
                batch = [t for t in batch if t["T"] <= chunk_end]
                if batch:
                    all_data.extend(batch)

            chunk_start = chunk_end
            logger.info(
                "[%s] Agg trades progress: %d trades fetched", symbol, len(all_data)
            )

        # Filter to exact time range
        all_data = [t for t in all_data if start_ms <= t["T"] <= end_ms]

        logger.info("[%s] Total aggregated trades: %d", symbol, len(all_data))

        if not all_data:
            return pd.DataFrame()

        df = pd.DataFrame(all_data)
        df = df.rename(columns={
            "a": "agg_trade_id",
            "p": "price",
            "q": "quantity",
            "f": "first_trade_id",
            "l": "last_trade_id",
            "T": "timestamp",
            "m": "is_buyer_maker",
        })
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["price"] = df["price"].astype(float)
        df["quantity"] = df["quantity"].astype(float)
        return df[[
            "timestamp", "agg_trade_id", "price", "quantity",
            "first_trade_id", "last_trade_id", "is_buyer_maker",
        ]]

    # ------------------------------------------------------------------ #
    #  Exchange Info & Symbol Listing                                       #
    # ------------------------------------------------------------------ #

    def get_exchange_info(self) -> dict:
        """Fetch full futures exchange information.

        Returns raw dict with symbols, rules, rate limits, etc.
        """
        return self._request(f"{self.FUTURES_BASE_URL}/fapi/v1/exchangeInfo")

    def get_futures_symbols(self) -> list[str]:
        """Get list of all active USDT-M perpetual futures symbols."""
        info = self.get_exchange_info()
        return sorted([
            s["symbol"]
            for s in info["symbols"]
            if s["status"] == "TRADING" and s["quoteAsset"] == "USDT"
        ])

    # ------------------------------------------------------------------ #
    #  Current Snapshots (non-historical)                                   #
    # ------------------------------------------------------------------ #

    def get_ticker_24hr(self, symbol: str | None = None) -> pd.DataFrame:
        """Fetch 24hr rolling ticker statistics.

        Args:
            symbol: Optional. If None, returns data for all symbols.

        Returns:
            DataFrame with price change, volume, and other 24hr stats.
        """
        params = {}
        if symbol:
            params["symbol"] = symbol

        data = self._request(
            f"{self.FUTURES_BASE_URL}/fapi/v1/ticker/24hr", params
        )
        if isinstance(data, dict):
            data = [data]

        df = pd.DataFrame(data)
        float_cols = [
            "priceChange", "priceChangePercent", "weightedAvgPrice",
            "lastPrice", "lastQty", "openPrice", "highPrice", "lowPrice",
            "volume", "quoteVolume",
        ]
        for col in float_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    def get_open_interest(self, symbol: str) -> dict:
        """Fetch current open interest for a symbol.

        Returns:
            dict with keys: symbol, openInterest, time
        """
        return self._request(
            f"{self.FUTURES_BASE_URL}/fapi/v1/openInterest",
            {"symbol": symbol},
        )

    def get_premium_index(self, symbol: str | None = None) -> pd.DataFrame:
        """Fetch current premium index (basis, funding rate, mark/index price).

        Shows the relationship between futures and spot prices.
        Useful for monitoring funding and basis in real-time.

        Args:
            symbol: Optional. If None, returns all symbols.

        Returns:
            DataFrame with markPrice, indexPrice, lastFundingRate, etc.
        """
        params = {}
        if symbol:
            params["symbol"] = symbol

        data = self._request(
            f"{self.FUTURES_BASE_URL}/fapi/v1/premiumIndex", params
        )
        if isinstance(data, dict):
            data = [data]

        df = pd.DataFrame(data)
        numeric_cols = [
            "markPrice", "indexPrice", "estimatedSettlePrice",
            "lastFundingRate", "interestRate",
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
        if "nextFundingTime" in df.columns:
            df["nextFundingTime"] = pd.to_datetime(
                df["nextFundingTime"], unit="ms", utc=True
            )
        return df

    def get_book_depth(
        self, symbol: str, limit: int = 20
    ) -> dict[str, pd.DataFrame]:
        """Fetch current order book depth.

        Args:
            symbol: Trading pair
            limit: Number of levels (5, 10, 20, 50, 100, 500, 1000)

        Returns:
            dict with 'bids' and 'asks' DataFrames, each with columns:
            price, quantity
        """
        data = self._request(
            f"{self.FUTURES_BASE_URL}/fapi/v1/depth",
            {"symbol": symbol, "limit": limit},
        )
        result = {}
        for side in ("bids", "asks"):
            df = pd.DataFrame(data[side], columns=["price", "quantity"])
            df["price"] = df["price"].astype(float)
            df["quantity"] = df["quantity"].astype(float)
            result[side] = df
        return result
