"""Binance USDT-M Futures adapter implementing FuturesDataSource.

Maps Binance-specific API responses to the canonical DataType schemas
defined in the domain layer.
"""

import logging

import pandas as pd

from ..domain.models import DataType
from .http_client import HttpClient, to_milliseconds

logger = logging.getLogger(__name__)

BASE_URL = "https://fapi.binance.com"


class BinanceFuturesSource:
    """Binance USDT-M Futures data source.

    Implements the ``FuturesDataSource`` protocol.
    """

    def __init__(
        self,
        max_retries: int = 3,
        rate_limit_sleep: float = 0.1,
    ):
        self._http = HttpClient(
            max_retries=max_retries,
            rate_limit_sleep=rate_limit_sleep,
        )

    @property
    def exchange(self) -> str:
        return "binance"

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ------------------------------------------------------------------ #
    #  Public: unified fetch entry point                                   #
    # ------------------------------------------------------------------ #

    def fetch(
        self,
        data_type: DataType,
        symbol: str,
        start_time: str | int,
        end_time: str | int,
        *,
        interval: str | None = None,
        period: str | None = None,
    ) -> pd.DataFrame:
        dispatcher = {
            DataType.OHLCV: self._fetch_ohlcv,
            DataType.INDEX_PRICE: self._fetch_index_price,
            DataType.MARK_PRICE: self._fetch_mark_price,
            DataType.FUNDING_RATE: self._fetch_funding_rate,
            DataType.OPEN_INTEREST: self._fetch_open_interest,
            DataType.LONG_SHORT_RATIO: self._fetch_long_short_ratio,
            DataType.TOP_LS_ACCOUNTS: self._fetch_top_ls_accounts,
            DataType.TOP_LS_POSITIONS: self._fetch_top_ls_positions,
            DataType.TAKER_BUY_SELL: self._fetch_taker_buy_sell,
        }
        handler = dispatcher[data_type]
        return handler(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            interval=interval,
            period=period,
        )

    # ------------------------------------------------------------------ #
    #  Internal: paginated fetch helpers                                   #
    # ------------------------------------------------------------------ #

    def _paginate_klines(
        self,
        endpoint: str,
        params_base: dict,
        start_ms: int,
        end_ms: int,
        limit: int = 1500,
    ) -> list[list]:
        all_data: list[list] = []
        current = start_ms

        while current < end_ms:
            params = {
                **params_base,
                "startTime": current,
                "endTime": end_ms,
                "limit": limit,
            }
            data = self._http.get(f"{BASE_URL}{endpoint}", params)
            if not data:
                break

            all_data.extend(data)
            logger.info("Fetched %d candles (total: %d)", len(data), len(all_data))

            if len(data) < limit:
                break
            current = data[-1][6] + 1  # close_time + 1

        return all_data

    def _paginate_records(
        self,
        endpoint: str,
        params_base: dict,
        start_ms: int,
        end_ms: int,
        limit: int,
        time_field: str = "timestamp",
    ) -> list[dict]:
        all_data: list[dict] = []
        current = start_ms

        while current < end_ms:
            params = {
                **params_base,
                "startTime": current,
                "endTime": end_ms,
                "limit": limit,
            }
            data = self._http.get(f"{BASE_URL}{endpoint}", params)
            if not data:
                break

            all_data.extend(data)
            logger.info("Fetched %d records (total: %d)", len(data), len(all_data))

            if len(data) < limit:
                break
            current = int(data[-1][time_field]) + 1

        return all_data

    # ------------------------------------------------------------------ #
    #  Internal: raw → canonical DataFrame converters                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _klines_to_df(raw: list[list], include_extra: bool = True) -> pd.DataFrame:
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

    @staticmethod
    def _records_to_ls_df(raw: list[dict]) -> pd.DataFrame:
        """Convert long/short ratio records to canonical DataFrame."""
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
    #  Fetch implementations per DataType                                  #
    # ------------------------------------------------------------------ #

    def _fetch_ohlcv(self, symbol, start_time, end_time, interval, **_) -> pd.DataFrame:
        raw = self._paginate_klines(
            "/fapi/v1/klines",
            {"symbol": symbol, "interval": interval},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
        )
        logger.info("[%s] Total klines fetched: %d", symbol, len(raw))
        return self._klines_to_df(raw)

    def _fetch_index_price(self, symbol, start_time, end_time, interval, **_) -> pd.DataFrame:
        raw = self._paginate_klines(
            "/fapi/v1/indexPriceKlines",
            {"pair": symbol, "interval": interval},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
        )
        logger.info("[%s] Total index price klines: %d", symbol, len(raw))
        return self._klines_to_df(raw, include_extra=False)

    def _fetch_mark_price(self, symbol, start_time, end_time, interval, **_) -> pd.DataFrame:
        raw = self._paginate_klines(
            "/fapi/v1/markPriceKlines",
            {"symbol": symbol, "interval": interval},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
        )
        logger.info("[%s] Total mark price klines: %d", symbol, len(raw))
        return self._klines_to_df(raw, include_extra=False)

    def _fetch_funding_rate(self, symbol, start_time, end_time, **_) -> pd.DataFrame:
        raw = self._paginate_records(
            "/fapi/v1/fundingRate",
            {"symbol": symbol},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
            limit=1000,
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

    def _fetch_open_interest(self, symbol, start_time, end_time, period, **_) -> pd.DataFrame:
        raw = self._paginate_records(
            "/futures/data/openInterestHist",
            {"symbol": symbol, "period": period},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
            limit=500,
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

    def _fetch_long_short_ratio(self, symbol, start_time, end_time, period, **_) -> pd.DataFrame:
        raw = self._paginate_records(
            "/futures/data/globalLongShortAccountRatio",
            {"symbol": symbol, "period": period},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
            limit=500,
        )
        logger.info("[%s] Total LS ratio records: %d", symbol, len(raw))
        return self._records_to_ls_df(raw)

    def _fetch_top_ls_accounts(self, symbol, start_time, end_time, period, **_) -> pd.DataFrame:
        raw = self._paginate_records(
            "/futures/data/topLongShortAccountRatio",
            {"symbol": symbol, "period": period},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
            limit=500,
        )
        logger.info("[%s] Total top trader LS (accounts): %d", symbol, len(raw))
        return self._records_to_ls_df(raw)

    def _fetch_top_ls_positions(self, symbol, start_time, end_time, period, **_) -> pd.DataFrame:
        raw = self._paginate_records(
            "/futures/data/topLongShortPositionRatio",
            {"symbol": symbol, "period": period},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
            limit=500,
        )
        logger.info("[%s] Total top trader LS (positions): %d", symbol, len(raw))
        return self._records_to_ls_df(raw)

    def _fetch_taker_buy_sell(self, symbol, start_time, end_time, period, **_) -> pd.DataFrame:
        raw = self._paginate_records(
            "/futures/data/takerlongshortRatio",
            {"symbol": symbol, "period": period},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
            limit=500,
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
