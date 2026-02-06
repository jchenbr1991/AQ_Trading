# backend/tests/market_data/test_tiger_source.py
"""Tests for TigerDataSource -- Phase 5 of Tiger Broker Adapter spec."""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from src.strategies.base import MarketData

# ---------------------------------------------------------------------------
# T029: Constructor validation
# ---------------------------------------------------------------------------


class TestTigerDataSourceConstructor:
    """Constructor validates credentials, account_id, symbols, env."""

    def test_valid_construction(self, tmp_path):
        from src.market_data.sources.tiger import TigerDataSource

        creds = tmp_path / "creds.props"
        creds.write_text("dummy")
        os.chmod(creds, 0o600)

        source = TigerDataSource(
            credentials_path=str(creds),
            account_id="ACC123",
            symbols=["AAPL"],
        )
        assert source._credentials_path == str(creds)
        assert source._account_id == "ACC123"
        assert source._connected is False

    def test_raises_for_missing_credentials(self, tmp_path):
        from src.market_data.sources.tiger import TigerDataSource

        with pytest.raises(ValueError, match="Credentials file not found"):
            TigerDataSource(
                credentials_path=str(tmp_path / "nonexistent.props"),
                account_id="ACC123",
                symbols=["AAPL"],
            )

    def test_raises_for_wrong_permissions(self, tmp_path):
        from src.market_data.sources.tiger import TigerDataSource

        creds = tmp_path / "creds.props"
        creds.write_text("dummy")
        os.chmod(creds, 0o644)

        with pytest.raises(ValueError, match="0600 permissions"):
            TigerDataSource(
                credentials_path=str(creds),
                account_id="ACC123",
                symbols=["AAPL"],
            )

    def test_raises_for_empty_account_id(self, tmp_path):
        from src.market_data.sources.tiger import TigerDataSource

        creds = tmp_path / "creds.props"
        creds.write_text("dummy")
        os.chmod(creds, 0o600)

        with pytest.raises(ValueError, match="account_id must be non-empty"):
            TigerDataSource(
                credentials_path=str(creds),
                account_id="",
                symbols=["AAPL"],
            )

    def test_raises_for_empty_symbols(self, tmp_path):
        from src.market_data.sources.tiger import TigerDataSource

        creds = tmp_path / "creds.props"
        creds.write_text("dummy")
        os.chmod(creds, 0o600)

        with pytest.raises(ValueError, match="symbols must be non-empty"):
            TigerDataSource(
                credentials_path=str(creds),
                account_id="ACC123",
                symbols=[],
            )

    def test_raises_for_invalid_env(self, tmp_path):
        from src.market_data.sources.tiger import TigerDataSource

        creds = tmp_path / "creds.props"
        creds.write_text("dummy")
        os.chmod(creds, 0o600)

        with pytest.raises(ValueError, match="env must be"):
            TigerDataSource(
                credentials_path=str(creds),
                account_id="ACC123",
                symbols=["AAPL"],
                env="DEV",
            )

    def test_default_max_symbols(self, tmp_path):
        from src.market_data.sources.tiger import TigerDataSource

        creds = tmp_path / "creds.props"
        creds.write_text("dummy")
        os.chmod(creds, 0o600)

        source = TigerDataSource(
            credentials_path=str(creds),
            account_id="ACC123",
            symbols=["AAPL"],
        )
        assert source._max_symbols == 50


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tiger_creds(tmp_path):
    creds = tmp_path / "creds.props"
    creds.write_text("dummy")
    os.chmod(creds, 0o600)
    return str(creds)


@pytest.fixture
def tiger_source(tiger_creds):
    from src.market_data.sources.tiger import TigerDataSource

    return TigerDataSource(
        credentials_path=tiger_creds,
        account_id="ACC123",
        symbols=["AAPL", "TSLA"],
        env="SANDBOX",
    )


def _patch_tiger_sdk(tiger_source):
    """Set up mocked Tiger SDK on a source for start()."""
    import src.market_data.sources.tiger as tiger_mod

    mock_push = MagicMock()
    mock_push.connect = MagicMock()
    mock_push.subscribe_quote = MagicMock()
    mock_push.unsubscribe_quote = MagicMock()
    mock_push.disconnect = MagicMock()
    mock_config = MagicMock()

    tiger_mod.TigerOpenClientConfig = MagicMock(return_value=mock_config)
    tiger_mod.PushClient = MagicMock(return_value=mock_push)

    return mock_push, mock_config


# ---------------------------------------------------------------------------
# T030: start() / stop()
# ---------------------------------------------------------------------------


class TestTigerDataSourceStartStop:
    """start/stop lifecycle with mocked PushClient."""

    async def test_start_subscribes_to_quotes(self, tiger_source):
        import src.market_data.sources.tiger as tiger_mod

        orig_cfg, orig_push = tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient
        try:
            mock_push, _ = _patch_tiger_sdk(tiger_source)
            await tiger_source.start()

            mock_push.connect.assert_called_once()
            mock_push.subscribe_quote.assert_called_once_with(["AAPL", "TSLA"])
            assert tiger_source._connected is True
        finally:
            tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient = orig_cfg, orig_push

    async def test_start_logs_warning_for_excess_symbols(self, tiger_creds, caplog):
        import src.market_data.sources.tiger as tiger_mod
        from src.market_data.sources.tiger import TigerDataSource

        symbols = [f"SYM{i}" for i in range(5)]
        source = TigerDataSource(
            credentials_path=tiger_creds,
            account_id="ACC123",
            symbols=symbols,
            max_symbols=3,
        )

        orig_cfg, orig_push = tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient
        try:
            mock_push, _ = _patch_tiger_sdk(source)
            with caplog.at_level(logging.WARNING):
                await source.start()

            mock_push.subscribe_quote.assert_called_once_with(["SYM0", "SYM1", "SYM2"])
            assert "max_symbols" in caplog.text.lower()
        finally:
            tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient = orig_cfg, orig_push

    async def test_stop_disconnects(self, tiger_source):
        import src.market_data.sources.tiger as tiger_mod

        orig_cfg, orig_push = tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient
        try:
            mock_push, _ = _patch_tiger_sdk(tiger_source)
            await tiger_source.start()
            await tiger_source.stop()

            assert tiger_source._connected is False
            mock_push.disconnect.assert_called_once()
        finally:
            tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient = orig_cfg, orig_push


# ---------------------------------------------------------------------------
# T031: quotes() async iterator + dedup
# ---------------------------------------------------------------------------


class TestTigerDataSourceQuotes:
    """quotes() yields MarketData from quote_changed callback."""

    async def test_quote_changed_enqueues_market_data(self, tiger_source):
        import src.market_data.sources.tiger as tiger_mod

        orig_cfg, orig_push = tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient
        try:
            _patch_tiger_sdk(tiger_source)
            await tiger_source.start()

            ts_ms = int(datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
            items = [
                {
                    "latest_price": 150.50,
                    "bid_price": 150.40,
                    "ask_price": 150.60,
                    "volume": 10000,
                    "timestamp": ts_ms,
                }
            ]
            tiger_source._quote_changed("AAPL", items, False)

            quote = await asyncio.wait_for(tiger_source._quote_queue.get(), timeout=2.0)
            assert isinstance(quote, MarketData)
            assert quote.symbol == "AAPL"
            assert quote.price == Decimal("150.50")
            assert quote.bid == Decimal("150.40")
            assert quote.ask == Decimal("150.60")
            assert quote.volume == 10000
        finally:
            tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient = orig_cfg, orig_push

    async def test_dedup_stale_timestamp(self, tiger_source):
        import src.market_data.sources.tiger as tiger_mod

        orig_cfg, orig_push = tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient
        try:
            _patch_tiger_sdk(tiger_source)
            await tiger_source.start()

            ts1 = int(datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
            ts2 = int(datetime(2024, 1, 15, 10, 0, 1, tzinfo=timezone.utc).timestamp() * 1000)
            base = {
                "latest_price": 150.50,
                "bid_price": 150.40,
                "ask_price": 150.60,
                "volume": 10000,
            }

            tiger_source._quote_changed("AAPL", [{**base, "timestamp": ts1}], False)
            tiger_source._quote_changed("AAPL", [{**base, "timestamp": ts1}], False)  # dup
            tiger_source._quote_changed("AAPL", [{**base, "timestamp": ts2}], False)  # new

            q1 = await asyncio.wait_for(tiger_source._quote_queue.get(), timeout=2.0)
            q2 = await asyncio.wait_for(tiger_source._quote_queue.get(), timeout=2.0)
            assert tiger_source._quote_queue.empty()
            assert q1.symbol == "AAPL"
            assert q2.symbol == "AAPL"
        finally:
            tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient = orig_cfg, orig_push

    async def test_quotes_async_iterator(self, tiger_source):
        import src.market_data.sources.tiger as tiger_mod

        orig_cfg, orig_push = tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient
        try:
            _patch_tiger_sdk(tiger_source)
            await tiger_source.start()

            ts_ms = int(datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
            items = [
                {
                    "latest_price": 100.0,
                    "bid_price": 99.90,
                    "ask_price": 100.10,
                    "volume": 5000,
                    "timestamp": ts_ms,
                }
            ]
            tiger_source._quote_changed("AAPL", items, False)

            collected = []
            async for md in tiger_source.quotes():
                collected.append(md)
                if len(collected) >= 1:
                    break

            assert len(collected) == 1
            assert collected[0].symbol == "AAPL"
        finally:
            tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient = orig_cfg, orig_push


# ---------------------------------------------------------------------------
# T032: subscribe() idempotent
# ---------------------------------------------------------------------------


class TestTigerDataSourceSubscribe:
    """subscribe() is idempotent and respects max_symbols."""

    async def test_subscribe_adds_new_symbols(self, tiger_source):
        import src.market_data.sources.tiger as tiger_mod

        orig_cfg, orig_push = tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient
        try:
            mock_push, _ = _patch_tiger_sdk(tiger_source)
            await tiger_source.start()
            mock_push.subscribe_quote.reset_mock()

            await tiger_source.subscribe(["GOOG", "MSFT"])

            mock_push.subscribe_quote.assert_called_once_with(["GOOG", "MSFT"])
            assert "GOOG" in tiger_source._subscribed_symbols
        finally:
            tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient = orig_cfg, orig_push

    async def test_subscribe_idempotent(self, tiger_source):
        import src.market_data.sources.tiger as tiger_mod

        orig_cfg, orig_push = tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient
        try:
            mock_push, _ = _patch_tiger_sdk(tiger_source)
            await tiger_source.start()
            mock_push.subscribe_quote.reset_mock()

            await tiger_source.subscribe(["AAPL", "TSLA"])

            mock_push.subscribe_quote.assert_not_called()
        finally:
            tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient = orig_cfg, orig_push

    async def test_subscribe_respects_max_symbols(self, tiger_creds, caplog):
        import src.market_data.sources.tiger as tiger_mod
        from src.market_data.sources.tiger import TigerDataSource

        source = TigerDataSource(
            credentials_path=tiger_creds,
            account_id="ACC123",
            symbols=["AAPL", "TSLA"],
            max_symbols=3,
        )

        orig_cfg, orig_push = tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient
        try:
            mock_push, _ = _patch_tiger_sdk(source)
            await source.start()
            mock_push.subscribe_quote.reset_mock()

            with caplog.at_level(logging.WARNING):
                await source.subscribe(["GOOG", "MSFT", "AMZN"])

            call_args = mock_push.subscribe_quote.call_args[0][0]
            assert len(call_args) == 1
            assert "max_symbols" in caplog.text.lower()
        finally:
            tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient = orig_cfg, orig_push


# ---------------------------------------------------------------------------
# T033: Missing quote fields
# ---------------------------------------------------------------------------


class TestTigerDataSourceMissingFields:
    """Quotes with missing required fields are skipped with warning."""

    async def test_missing_latest_price_skipped(self, tiger_source, caplog):
        import src.market_data.sources.tiger as tiger_mod

        orig_cfg, orig_push = tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient
        try:
            _patch_tiger_sdk(tiger_source)
            await tiger_source.start()

            ts_ms = int(datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
            items = [
                {
                    "latest_price": None,
                    "bid_price": 150.40,
                    "ask_price": 150.60,
                    "volume": 10000,
                    "timestamp": ts_ms,
                }
            ]

            with caplog.at_level(logging.WARNING):
                tiger_source._quote_changed("AAPL", items, False)

            assert tiger_source._quote_queue.empty()
            assert "missing" in caplog.text.lower() or "skip" in caplog.text.lower()
        finally:
            tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient = orig_cfg, orig_push

    async def test_missing_timestamp_skipped(self, tiger_source, caplog):
        import src.market_data.sources.tiger as tiger_mod

        orig_cfg, orig_push = tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient
        try:
            _patch_tiger_sdk(tiger_source)
            await tiger_source.start()

            items = [
                {"latest_price": 150.50, "bid_price": 150.40, "ask_price": 150.60, "volume": 10000}
            ]

            with caplog.at_level(logging.WARNING):
                tiger_source._quote_changed("AAPL", items, False)

            assert tiger_source._quote_queue.empty()
        finally:
            tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient = orig_cfg, orig_push

    async def test_bad_item_does_not_discard_batch(self, tiger_source):
        """A malformed item in a batch should not prevent processing later items."""
        import src.market_data.sources.tiger as tiger_mod

        orig_cfg, orig_push = tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient
        try:
            _patch_tiger_sdk(tiger_source)
            await tiger_source.start()

            ts1 = int(datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
            ts2 = int(datetime(2024, 1, 15, 10, 0, 1, tzinfo=timezone.utc).timestamp() * 1000)

            items = [
                # Bad item (missing latest_price)
                {
                    "latest_price": None,
                    "bid_price": 150.40,
                    "ask_price": 150.60,
                    "volume": 10000,
                    "timestamp": ts1,
                },
                # Good item
                {
                    "latest_price": 151.00,
                    "bid_price": 150.90,
                    "ask_price": 151.10,
                    "volume": 5000,
                    "timestamp": ts2,
                },
            ]

            tiger_source._quote_changed("AAPL", items, False)

            # call_soon_threadsafe schedules on next loop iteration
            await asyncio.sleep(0)

            # Good item should still be enqueued despite bad first item
            assert not tiger_source._quote_queue.empty()
            quote = tiger_source._quote_queue.get_nowait()
            assert quote.price == Decimal("151.00")
        finally:
            tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient = orig_cfg, orig_push


# ---------------------------------------------------------------------------
# T042: Performance assertion (SC-007)
# ---------------------------------------------------------------------------


class TestTigerDataSourcePerformance:
    """Quote callback to quotes() yield within 2s (SC-007)."""

    async def test_quote_callback_to_yield_within_2s(self, tiger_source):
        import src.market_data.sources.tiger as tiger_mod

        orig_cfg, orig_push = tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient
        try:
            _patch_tiger_sdk(tiger_source)
            await tiger_source.start()

            ts_ms = int(datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
            items = [
                {
                    "latest_price": 150.50,
                    "bid_price": 150.40,
                    "ask_price": 150.60,
                    "volume": 10000,
                    "timestamp": ts_ms,
                }
            ]

            start_time = time.monotonic()
            tiger_source._quote_changed("AAPL", items, False)
            quote = await asyncio.wait_for(tiger_source._quote_queue.get(), timeout=2.0)
            elapsed = time.monotonic() - start_time

            assert elapsed < 2.0, f"Quote callback to yield took {elapsed:.3f}s"
            assert isinstance(quote, MarketData)
        finally:
            tiger_mod.TigerOpenClientConfig, tiger_mod.PushClient = orig_cfg, orig_push
