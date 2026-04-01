"""
GRVT Exchange Client

A Python client for the GRVT (Gravity Markets) cryptocurrency exchange API.
Supports authentication, balance queries, orderbook retrieval, order placement,
and order status checks.

API Reference: https://api-docs.grvt.io/
"""

from __future__ import annotations

import json
import time
import logging
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from enum import Enum
from http.cookiejar import CookieJar
from http.cookies import SimpleCookie
from typing import Any

import requests

try:
    from eth_account import Account
    from eth_account.messages import encode_typed_data

    _HAS_ETH_ACCOUNT = True
except ImportError:
    _HAS_ETH_ACCOUNT = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PRICE_MULTIPLIER = 1_000_000_000

# EIP-712 domain for order signing
EIP712_DOMAIN_NAME = "GRVT Exchange"
EIP712_DOMAIN_VERSION = "0"

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class GrvtEnv(str, Enum):
    """GRVT API environments."""

    PROD = "prod"
    TESTNET = "testnet"
    STAGING = "staging"
    DEV = "dev"


class TimeInForce(str, Enum):
    """Order time-in-force options."""

    GOOD_TILL_TIME = "GOOD_TILL_TIME"
    ALL_OR_NONE = "ALL_OR_NONE"
    IMMEDIATE_OR_CANCEL = "IMMEDIATE_OR_CANCEL"
    FILL_OR_KILL = "FILL_OR_KILL"


class OrderStatus(str, Enum):
    """Possible order statuses."""

    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class Kind(str, Enum):
    """Instrument kinds."""

    PERPETUAL = "PERPETUAL"
    FUTURE = "FUTURE"
    CALL = "CALL"
    PUT = "PUT"


# Mapping from TimeInForce to the uint8 value used in EIP-712 signing
_TIF_TO_UINT8: dict[TimeInForce, int] = {
    TimeInForce.GOOD_TILL_TIME: 1,
    TimeInForce.ALL_OR_NONE: 2,
    TimeInForce.IMMEDIATE_OR_CANCEL: 3,
    TimeInForce.FILL_OR_KILL: 4,
}

# Chain IDs per environment
_CHAIN_IDS: dict[GrvtEnv, int] = {
    GrvtEnv.PROD: 325,
    GrvtEnv.TESTNET: 326,
    GrvtEnv.DEV: 327,
    GrvtEnv.STAGING: 328,
}


# ---------------------------------------------------------------------------
# Environment configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _EnvConfig:
    edge_url: str
    trade_url: str
    market_data_url: str
    chain_id: int


_ENV_CONFIGS: dict[GrvtEnv, _EnvConfig] = {
    GrvtEnv.PROD: _EnvConfig(
        edge_url="https://edge.grvt.io",
        trade_url="https://trades.grvt.io",
        market_data_url="https://market-data.grvt.io",
        chain_id=325,
    ),
    GrvtEnv.TESTNET: _EnvConfig(
        edge_url="https://edge.testnet.grvt.io",
        trade_url="https://trades.testnet.grvt.io",
        market_data_url="https://market-data.testnet.grvt.io",
        chain_id=326,
    ),
    GrvtEnv.STAGING: _EnvConfig(
        edge_url="https://edge.staging.gravitymarkets.io",
        trade_url="https://trades.staging.gravitymarkets.io",
        market_data_url="https://market-data.staging.gravitymarkets.io",
        chain_id=328,
    ),
    GrvtEnv.DEV: _EnvConfig(
        edge_url="https://edge.dev.gravitymarkets.io",
        trade_url="https://trades.dev.gravitymarkets.io",
        market_data_url="https://market-data.dev.gravitymarkets.io",
        chain_id=327,
    ),
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class GrvtError(Exception):
    """Raised when the GRVT API returns an error response."""

    def __init__(self, code: int, message: str, status: int | None = None):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(f"GRVT API Error {code}: {message}")


class GrvtAuthError(GrvtError):
    """Raised on authentication failures."""


# ---------------------------------------------------------------------------
# EIP-712 signing helpers
# ---------------------------------------------------------------------------


def _build_eip712_order_data(
    order_payload: dict[str, Any],
    instruments: dict[str, dict[str, Any]],
    chain_id: int,
    nonce: int,
    expiration: int,
) -> tuple[dict, dict, dict]:
    """Build the EIP-712 domain, types, and message for order signing.

    Returns (domain_data, types, message_data).
    """
    domain_data = {
        "name": EIP712_DOMAIN_NAME,
        "version": EIP712_DOMAIN_VERSION,
        "chainId": chain_id,
    }

    types = {
        "Order": [
            {"name": "subAccountID", "type": "uint64"},
            {"name": "isMarket", "type": "bool"},
            {"name": "timeInForce", "type": "uint8"},
            {"name": "postOnly", "type": "bool"},
            {"name": "reduceOnly", "type": "bool"},
            {"name": "legs", "type": "OrderLeg[]"},
            {"name": "nonce", "type": "uint32"},
            {"name": "expiration", "type": "int64"},
        ],
        "OrderLeg": [
            {"name": "assetID", "type": "uint256"},
            {"name": "contractSize", "type": "uint64"},
            {"name": "limitPrice", "type": "uint64"},
            {"name": "isBuyingContract", "type": "bool"},
        ],
    }

    legs_data = []
    for leg in order_payload.get("legs", []):
        instrument_name = leg["instrument"]
        inst_info = instruments.get(instrument_name)
        if inst_info is None:
            raise ValueError(
                f"Instrument '{instrument_name}' not found. "
                "Call fetch_instruments() first to populate instrument metadata."
            )

        base_decimals = inst_info["base_decimals"]
        asset_id = int(inst_info["instrument_hash"], 0)

        size_decimal = Decimal(str(leg["size"]))
        contract_size = int(size_decimal * (Decimal(10) ** base_decimals))

        limit_price_raw = leg.get("limit_price") or "0"
        limit_price_decimal = Decimal(str(limit_price_raw))
        limit_price = int(limit_price_decimal * PRICE_MULTIPLIER)

        legs_data.append(
            {
                "assetID": asset_id,
                "contractSize": contract_size,
                "limitPrice": limit_price,
                "isBuyingContract": leg["is_buying_asset"],
            }
        )

    sub_account_id = int(order_payload["sub_account_id"])
    tif_value = _TIF_TO_UINT8.get(
        TimeInForce(order_payload["time_in_force"]), 1
    )

    message_data = {
        "subAccountID": sub_account_id,
        "isMarket": order_payload.get("is_market", False),
        "timeInForce": tif_value,
        "postOnly": order_payload.get("post_only", False),
        "reduceOnly": order_payload.get("reduce_only", False),
        "legs": legs_data,
        "nonce": nonce,
        "expiration": expiration,
    }

    return domain_data, types, message_data


def sign_order(
    order_payload: dict[str, Any],
    private_key: str,
    instruments: dict[str, dict[str, Any]],
    chain_id: int,
    nonce: int | None = None,
    expiration: int | None = None,
) -> dict[str, Any]:
    """Sign an order using EIP-712 and return the signature dict.

    Requires the ``eth_account`` package (``pip install eth-account``).

    Args:
        order_payload: The order dict (sub_account_id, legs, time_in_force, …).
        private_key: Hex-encoded private key for signing.
        instruments: Mapping of instrument name → instrument metadata dict
                     (must contain ``instrument_hash`` and ``base_decimals``).
        chain_id: The chain ID for the target environment.
        nonce: Optional nonce (defaults to current unix timestamp in ns).
        expiration: Optional expiration timestamp in seconds.  Defaults to
                    ``now + 86400`` (24 h).

    Returns:
        A dict with keys ``signer``, ``r``, ``s``, ``v``, ``expiration``, ``nonce``.
    """
    if not _HAS_ETH_ACCOUNT:
        raise ImportError(
            "The 'eth-account' package is required for order signing. "
            "Install it with: pip install eth-account"
        )

    now = int(time.time())
    if nonce is None:
        nonce = int(time.time_ns())
    if expiration is None:
        expiration = now + 86400  # 24 hours

    domain_data, types, message_data = _build_eip712_order_data(
        order_payload, instruments, chain_id, nonce, expiration
    )

    signable = encode_typed_data(
        domain_data=domain_data,
        types=types,
        primary_type="Order",
        message_data=message_data,
    )
    signed = Account.sign_message(signable, private_key=private_key)

    return {
        "signer": Account.from_key(private_key).address,
        "r": hex(signed.r),
        "s": hex(signed.s),
        "v": signed.v,
        "expiration": str(expiration),
        "nonce": nonce,
    }


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------


class GrvtClient:
    """Client for the GRVT (Gravity Markets) exchange REST API.

    Args:
        env: Target environment (``prod``, ``testnet``, ``staging``, ``dev``).
        api_key: GRVT API key obtained from the UI.
        private_key: Hex-encoded private key for EIP-712 order signing.
                     Required only for :meth:`post_order`.
        trading_account_id: The sub-account (trading account) ID.
                            Required for authenticated trading endpoints.
        auto_login: If ``True``, authenticate on first request automatically.

    Example::

        client = GrvtClient(
            env="testnet",
            api_key="YOUR_API_KEY",
            private_key="0xYOUR_PRIVATE_KEY",
            trading_account_id="123456789",
        )
        balance = client.fetch_balance()
        book = client.fetch_orderbook("BTC_USDT_Perp")
    """

    def __init__(
        self,
        env: str | GrvtEnv = GrvtEnv.TESTNET,
        api_key: str = "",
        private_key: str = "",
        trading_account_id: str = "",
        auto_login: bool = True,
    ) -> None:
        if isinstance(env, str):
            env = GrvtEnv(env)
        self._env = env
        self._config = _ENV_CONFIGS[env]
        self._api_key = api_key
        self._private_key = private_key
        self._trading_account_id = trading_account_id
        self._auto_login = auto_login

        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

        self._cookie: str | None = None
        self._cookie_expiry: float = 0.0
        self._account_id: str | None = None

        # Instrument cache: instrument_name -> instrument metadata dict
        self._instruments: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def login(self) -> None:
        """Authenticate with the GRVT API and obtain a session cookie.

        The session cookie (``gravity=…``) and ``X-Grvt-Account-Id`` header
        are stored internally and sent with subsequent requests.

        Raises:
            GrvtAuthError: If authentication fails.
        """
        url = f"{self._config.edge_url}/auth/api_key/login"
        payload = {"api_key": self._api_key}

        resp = self._session.post(url, json=payload)

        if resp.status_code != 200:
            raise GrvtAuthError(
                code=resp.status_code,
                message=f"Authentication failed: {resp.text}",
                status=resp.status_code,
            )

        # Extract the gravity cookie from Set-Cookie header
        set_cookie_header = resp.headers.get("Set-Cookie", "")
        cookie = SimpleCookie()
        cookie.load(set_cookie_header)

        gravity_morsel = cookie.get("gravity")
        if gravity_morsel is None:
            raise GrvtAuthError(
                code=0,
                message="No 'gravity' cookie in authentication response.",
            )

        self._cookie = gravity_morsel.value
        expires_str = gravity_morsel.get("expires", "")
        if expires_str:
            try:
                from email.utils import parsedate_to_datetime

                self._cookie_expiry = parsedate_to_datetime(
                    expires_str
                ).timestamp()
            except Exception:
                self._cookie_expiry = time.time() + 86400
        else:
            self._cookie_expiry = time.time() + 86400

        self._session.cookies.set("gravity", self._cookie)

        # Extract X-Grvt-Account-Id
        account_id = resp.headers.get("X-Grvt-Account-Id", "").strip()
        if account_id:
            self._account_id = account_id
            self._session.headers["X-Grvt-Account-Id"] = account_id

        logger.info("GRVT authentication successful (env=%s)", self._env.value)

    def _ensure_auth(self) -> None:
        """Refresh authentication cookie if expired or not yet obtained."""
        needs_refresh = (
            self._cookie is None
            or time.time() >= self._cookie_expiry - 5
        )
        if needs_refresh:
            if self._auto_login:
                self.login()
            else:
                raise GrvtAuthError(
                    code=0,
                    message=(
                        "Not authenticated. Call login() or set auto_login=True."
                    ),
                )

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _post_trade(
        self, path: str, payload: dict[str, Any], auth: bool = True
    ) -> dict[str, Any]:
        """Send a POST request to the trading API.

        Args:
            path: Endpoint path (e.g. ``/full/v1/create_order``).
            payload: JSON request body.
            auth: Whether to attach the session cookie.

        Returns:
            Parsed JSON response dict.
        """
        if auth:
            self._ensure_auth()
        url = f"{self._config.trade_url}{path}"
        resp = self._session.post(url, json=payload)
        return self._handle_response(resp)

    def _post_market_data(
        self, path: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a POST request to the market data API (no auth required).

        Args:
            path: Endpoint path (e.g. ``/full/v1/book``).
            payload: JSON request body.

        Returns:
            Parsed JSON response dict.
        """
        url = f"{self._config.market_data_url}{path}"
        resp = self._session.post(url, json=payload)
        return self._handle_response(resp)

    @staticmethod
    def _handle_response(resp: requests.Response) -> dict[str, Any]:
        """Parse a JSON response and raise on errors."""
        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError):
            raise GrvtError(
                code=resp.status_code,
                message=f"Invalid JSON response: {resp.text[:500]}",
                status=resp.status_code,
            )

        if resp.status_code != 200:
            code = data.get("code", resp.status_code)
            message = data.get("message", resp.text)
            raise GrvtError(code=code, message=message, status=resp.status_code)

        # Some error responses are 200 but contain an error body
        if "code" in data and data.get("code", 0) != 0:
            raise GrvtError(
                code=data["code"],
                message=data.get("message", "Unknown error"),
                status=resp.status_code,
            )

        return data

    # ------------------------------------------------------------------
    # Instrument helpers
    # ------------------------------------------------------------------

    def fetch_instruments(
        self, is_active: bool | None = True
    ) -> list[dict[str, Any]]:
        """Fetch all available instruments and cache their metadata.

        This must be called before :meth:`post_order` so that instrument
        metadata (``instrument_hash``, ``base_decimals``) is available
        for EIP-712 signing.

        Args:
            is_active: If ``True``, return only active instruments.

        Returns:
            A list of instrument dicts.
        """
        payload: dict[str, Any] = {}
        if is_active is not None:
            payload["is_active"] = is_active

        data = self._post_market_data("/full/v1/all_instruments", payload)
        instruments = data.get("result", [])

        for inst in instruments:
            name = inst.get("instrument", "")
            if name:
                self._instruments[name] = inst

        return instruments

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def fetch_balance(
        self, sub_account_id: str | None = None
    ) -> dict[str, Any]:
        """Fetch the account balance (sub-account / trading account summary).

        Args:
            sub_account_id: The trading sub-account ID. Defaults to the
                ``trading_account_id`` provided at construction.

        Returns:
            A dict containing the sub-account summary with fields such as
            ``total_equity``, ``available_balance``, ``spot_balances``,
            ``positions``, etc.

        Raises:
            GrvtError: On API error.

        Example response structure::

            {
                "result": {
                    "event_time": "1234567890000000000",
                    "sub_account_id": "123456789",
                    "margin_type": "SIMPLE_CROSS_MARGIN",
                    "settle_currency": "USDT",
                    "total_equity": "10000.0",
                    "initial_margin": "100.0",
                    "maintenance_margin": "50.0",
                    "available_balance": "9850.0",
                    "spot_balances": [
                        {"currency": "USDT", "balance": "10000.0", "index_price": "1.0"}
                    ],
                    "positions": [...]
                }
            }
        """
        sa_id = sub_account_id or self._trading_account_id
        if not sa_id:
            raise ValueError(
                "sub_account_id is required. Provide it as an argument or "
                "set trading_account_id in the constructor."
            )
        payload = {"sub_account_id": sa_id}
        return self._post_trade("/full/v1/account_summary", payload)

    def fetch_funding_balance(self) -> dict[str, Any]:
        """Fetch the funding (main) account balance.

        Returns:
            A dict containing the funding account summary with fields such as
            ``total_equity``, ``spot_balances``, and fee tier info.

        Example response structure::

            {
                "result": {
                    "main_account_id": "0x...",
                    "total_equity": "50000.0",
                    "spot_balances": [
                        {"currency": "USDT", "balance": "50000.0", "index_price": "1.0"}
                    ]
                },
                "tier": {
                    "tier": 1,
                    "futures_taker_fee": 500,
                    "futures_maker_fee": 200,
                    ...
                }
            }
        """
        return self._post_trade("/full/v1/funding_account_summary", {})

    def fetch_orderbook(
        self, instrument: str, depth: int = 10
    ) -> dict[str, Any]:
        """Fetch the aggregated orderbook for an instrument.

        This endpoint does not require authentication.

        Args:
            instrument: Instrument name (e.g. ``"BTC_USDT_Perp"``).
            depth: Number of price levels to retrieve (max 10 per the API).

        Returns:
            A dict containing ``bids`` and ``asks``, each a list of
            ``{"price": str, "size": str, "num_orders": int}`` entries.

        Example response structure::

            {
                "result": {
                    "event_time": "1234567890000000000",
                    "instrument": "BTC_USDT_Perp",
                    "bids": [
                        {"price": "65000.0", "size": "1.5", "num_orders": 3}
                    ],
                    "asks": [
                        {"price": "65001.0", "size": "2.0", "num_orders": 5}
                    ]
                }
            }
        """
        payload = {"instrument": instrument, "depth": depth}
        return self._post_market_data("/full/v1/book", payload)

    def post_order(
        self,
        instrument: str,
        size: str,
        is_buying_asset: bool,
        limit_price: str | None = None,
        time_in_force: str | TimeInForce = TimeInForce.GOOD_TILL_TIME,
        sub_account_id: str | None = None,
        is_market: bool = False,
        post_only: bool = False,
        reduce_only: bool = False,
        client_order_id: str = "",
        nonce: int | None = None,
        expiration: int | None = None,
    ) -> dict[str, Any]:
        """Place an order on the GRVT exchange.

        Requires ``private_key`` to be set for EIP-712 order signing.
        Instrument metadata must be available — call :meth:`fetch_instruments`
        before the first order if the cache is empty.

        Args:
            instrument: Instrument name (e.g. ``"BTC_USDT_Perp"``).
            size: Order size as a decimal string (e.g. ``"0.1"``).
            is_buying_asset: ``True`` for buy, ``False`` for sell.
            limit_price: Limit price as a decimal string.  Required for
                limit orders (non-market).
            time_in_force: Time-in-force policy.
            sub_account_id: Trading sub-account ID. Defaults to constructor value.
            is_market: ``True`` for market order.
            post_only: If ``True``, the order will only be placed as a maker.
            reduce_only: If ``True``, the order will only reduce an existing position.
            client_order_id: Optional client-specified order ID.
            nonce: Optional nonce for signing (defaults to current ns timestamp).
            expiration: Optional expiration unix timestamp in seconds
                        (defaults to now + 24h).

        Returns:
            The created order as returned by the API.

        Raises:
            ImportError: If ``eth-account`` is not installed.
            ValueError: If required parameters are missing.
            GrvtError: On API error.

        Example::

            client.fetch_instruments()
            result = client.post_order(
                instrument="BTC_USDT_Perp",
                size="0.01",
                is_buying_asset=True,
                limit_price="60000",
                time_in_force="GOOD_TILL_TIME",
            )
        """
        if not self._private_key:
            raise ValueError(
                "private_key is required for order signing. "
                "Provide it in the GrvtClient constructor."
            )

        sa_id = sub_account_id or self._trading_account_id
        if not sa_id:
            raise ValueError(
                "sub_account_id is required. Provide it as an argument or "
                "set trading_account_id in the constructor."
            )

        if isinstance(time_in_force, str):
            time_in_force = TimeInForce(time_in_force)

        # Auto-fetch instruments if cache is empty
        if not self._instruments:
            self.fetch_instruments()

        if instrument not in self._instruments:
            raise ValueError(
                f"Unknown instrument '{instrument}'. "
                "Available instruments: "
                + ", ".join(sorted(self._instruments.keys())[:20])
            )

        # Build order payload
        leg = {
            "instrument": instrument,
            "size": size,
            "limit_price": limit_price or "0",
            "is_buying_asset": is_buying_asset,
        }

        order_payload: dict[str, Any] = {
            "sub_account_id": sa_id,
            "is_market": is_market,
            "time_in_force": time_in_force.value,
            "post_only": post_only,
            "reduce_only": reduce_only,
            "legs": [leg],
        }

        # Sign the order via EIP-712
        sig = sign_order(
            order_payload=order_payload,
            private_key=self._private_key,
            instruments=self._instruments,
            chain_id=self._config.chain_id,
            nonce=nonce,
            expiration=expiration,
        )

        # Assemble the full order for the API
        order = {
            "sub_account_id": sa_id,
            "is_market": is_market,
            "time_in_force": time_in_force.value,
            "post_only": post_only,
            "reduce_only": reduce_only,
            "legs": [leg],
            "signature": sig,
            "metadata": {
                "client_order_id": client_order_id,
            },
        }

        request_body = {"order": order}
        return self._post_trade("/full/v1/create_order", request_body)

    def fetch_order_status(
        self,
        order_id: str | None = None,
        client_order_id: str | None = None,
        sub_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Fetch the status of an order.

        Either ``order_id`` or ``client_order_id`` must be provided.

        Args:
            order_id: The exchange-assigned order ID.
            client_order_id: The client-specified order ID.
            sub_account_id: Trading sub-account ID. Defaults to constructor value.

        Returns:
            A dict containing the order details including state information.

        Example response structure::

            {
                "result": {
                    "order_id": "0x1028403",
                    "sub_account_id": "123456789",
                    "time_in_force": "GOOD_TILL_TIME",
                    "legs": [...],
                    "metadata": {"client_order_id": "my-order-1"},
                    "state": {
                        "status": "OPEN",
                        "reject_reason": "UNSPECIFIED",
                        "book_size": ["0.1"],
                        "traded_size": ["0.0"],
                        "update_time": "1234567890000000000"
                    }
                }
            }
        """
        if not order_id and not client_order_id:
            raise ValueError(
                "Either order_id or client_order_id must be provided."
            )

        sa_id = sub_account_id or self._trading_account_id
        if not sa_id:
            raise ValueError(
                "sub_account_id is required. Provide it as an argument or "
                "set trading_account_id in the constructor."
            )

        payload: dict[str, Any] = {"sub_account_id": sa_id}
        if order_id:
            payload["order_id"] = order_id
        if client_order_id:
            payload["client_order_id"] = client_order_id

        return self._post_trade("/full/v1/order", payload)

    # ------------------------------------------------------------------
    # Additional convenience methods
    # ------------------------------------------------------------------

    def fetch_open_orders(
        self,
        sub_account_id: str | None = None,
        instrument: str | None = None,
    ) -> dict[str, Any]:
        """Fetch all open orders for the sub-account.

        Args:
            sub_account_id: Trading sub-account ID. Defaults to constructor value.
            instrument: Optional instrument filter.

        Returns:
            A dict with a ``result`` list of open orders.
        """
        sa_id = sub_account_id or self._trading_account_id
        if not sa_id:
            raise ValueError(
                "sub_account_id is required. Provide it as an argument or "
                "set trading_account_id in the constructor."
            )

        payload: dict[str, Any] = {"sub_account_id": sa_id}
        if instrument:
            payload["instrument"] = instrument
        return self._post_trade("/full/v1/open_orders", payload)

    def cancel_order(
        self,
        order_id: str | None = None,
        client_order_id: str | None = None,
        sub_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Cancel an order.

        Either ``order_id`` or ``client_order_id`` must be provided.

        Args:
            order_id: The exchange-assigned order ID.
            client_order_id: The client-specified order ID.
            sub_account_id: Trading sub-account ID. Defaults to constructor value.

        Returns:
            The API response confirming cancellation.
        """
        if not order_id and not client_order_id:
            raise ValueError(
                "Either order_id or client_order_id must be provided."
            )

        sa_id = sub_account_id or self._trading_account_id
        if not sa_id:
            raise ValueError(
                "sub_account_id is required. Provide it as an argument or "
                "set trading_account_id in the constructor."
            )

        payload: dict[str, Any] = {"sub_account_id": sa_id}
        if order_id:
            payload["order_id"] = order_id
        if client_order_id:
            payload["client_order_id"] = client_order_id

        return self._post_trade("/full/v1/cancel_order", payload)

    def cancel_all_orders(
        self,
        sub_account_id: str | None = None,
        instrument: str | None = None,
    ) -> dict[str, Any]:
        """Cancel all open orders for the sub-account.

        Args:
            sub_account_id: Trading sub-account ID. Defaults to constructor value.
            instrument: Optional instrument filter.

        Returns:
            The API response confirming cancellation.
        """
        sa_id = sub_account_id or self._trading_account_id
        if not sa_id:
            raise ValueError(
                "sub_account_id is required. Provide it as an argument or "
                "set trading_account_id in the constructor."
            )

        payload: dict[str, Any] = {"sub_account_id": sa_id}
        if instrument:
            payload["instrument"] = instrument
        return self._post_trade("/full/v1/cancel_all_orders", payload)
