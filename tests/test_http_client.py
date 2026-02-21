"""Tests for market_data.infra.http_client."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from market_data.infra.http_client import HttpClient, to_milliseconds


# ------------------------------------------------------------------ #
#  to_milliseconds                                                     #
# ------------------------------------------------------------------ #


class TestToMilliseconds:
    def test_int_passthrough(self):
        assert to_milliseconds(1700000000000) == 1700000000000

    def test_float_truncated(self):
        assert to_milliseconds(1700000000000.5) == 1700000000000

    def test_date_string(self):
        ms = to_milliseconds("2024-01-01")
        expected = int(
            datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
        )
        assert ms == expected

    def test_datetime_string(self):
        ms = to_milliseconds("2024-01-01 12:30:00")
        expected = int(
            datetime(2024, 1, 1, 12, 30, 0, tzinfo=timezone.utc).timestamp()
            * 1000
        )
        assert ms == expected

    def test_datetime_object_naive(self):
        dt = datetime(2024, 6, 15, 10, 0, 0)
        ms = to_milliseconds(dt)
        expected = int(
            dt.replace(tzinfo=timezone.utc).timestamp() * 1000
        )
        assert ms == expected

    def test_datetime_object_aware(self):
        dt = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        ms = to_milliseconds(dt)
        assert ms == int(dt.timestamp() * 1000)

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError, match="Unsupported datetime format"):
            to_milliseconds("not-a-date")

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError, match="Cannot convert"):
            to_milliseconds([1, 2, 3])


# ------------------------------------------------------------------ #
#  HttpClient                                                          #
# ------------------------------------------------------------------ #


class TestHttpClient:
    def test_successful_request(self):
        client = HttpClient(rate_limit_sleep=0)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"test": "data"}]

        with patch.object(client.session, "get", return_value=mock_resp):
            result = client.get("https://example.com/api")
            assert result == [{"test": "data"}]

    def test_retry_on_429(self):
        client = HttpClient(max_retries=3, rate_limit_sleep=0)

        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.text = "Too many requests"

        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {"ok": True}

        with patch.object(
            client.session, "get", side_effect=[rate_limited, success]
        ), patch("market_data.infra.http_client.time.sleep"):
            result = client.get("https://example.com/api")
            assert result == {"ok": True}

    def test_raises_on_server_error(self):
        client = HttpClient(rate_limit_sleep=0)
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        with patch.object(client.session, "get", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="HTTP 500"):
                client.get("https://example.com/api")

    def test_raises_on_ip_ban(self):
        client = HttpClient(rate_limit_sleep=0)
        mock_resp = MagicMock()
        mock_resp.status_code = 418
        mock_resp.text = "IP banned"

        with patch.object(client.session, "get", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="IP banned"):
                client.get("https://example.com/api")

    def test_context_manager(self):
        with HttpClient() as client:
            assert client.session is not None
