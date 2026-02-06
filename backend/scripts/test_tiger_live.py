#!/usr/bin/env python3
"""Live test script for Tiger Trading broker and market data.

Usage:
    cd backend
    python scripts/test_tiger_live.py
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)

from src.broker.tiger_broker import TigerBroker  # noqa: E402
from src.market_data.sources.tiger import TigerDataSource  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Use absolute path to credentials file (relative to repo root)
REPO_ROOT = Path(__file__).parent.parent.parent
CREDENTIALS_PATH = str(REPO_ROOT / "config/brokers/tiger_openapi_config.properties")
ACCOUNT_ID = "21552525095632360"
TEST_SYMBOLS = ["AAPL", "TSLA", "NVDA"]


async def test_market_data():
    """Test TigerDataSource market data streaming."""
    logger.info("=" * 60)
    logger.info("Testing TigerDataSource - Market Data")
    logger.info("=" * 60)

    source = TigerDataSource(
        credentials_path=CREDENTIALS_PATH,
        account_id=ACCOUNT_ID,
        symbols=TEST_SYMBOLS,
        env="PROD",
    )

    try:
        logger.info(f"Connecting to Tiger market data for {TEST_SYMBOLS}...")
        await source.start()
        logger.info("Connected! Waiting for quotes...")

        # Collect 10 quotes or timeout after 30 seconds
        collected = []
        timeout = 30

        async def collect_quotes():
            async for quote in source.quotes():
                logger.info(
                    f"Quote: {quote.symbol} | "
                    f"price={quote.price} | "
                    f"bid={quote.bid} | "
                    f"ask={quote.ask} | "
                    f"vol={quote.volume} | "
                    f"ts={quote.timestamp}"
                )
                collected.append(quote)
                if len(collected) >= 10:
                    break

        try:
            await asyncio.wait_for(collect_quotes(), timeout=timeout)
            logger.info(f"SUCCESS: Collected {len(collected)} quotes")
        except TimeoutError:
            if collected:
                logger.info(f"Timeout after {timeout}s, collected {len(collected)} quotes")
            else:
                logger.warning(f"No quotes received in {timeout}s - market may be closed")

    except Exception as e:
        logger.error(f"Market data test failed: {e}", exc_info=True)
        return False
    finally:
        await source.stop()
        logger.info("TigerDataSource stopped")

    return len(collected) > 0


async def test_broker_connection():
    """Test TigerBroker connection and account query."""
    logger.info("=" * 60)
    logger.info("Testing TigerBroker - Connection & Account")
    logger.info("=" * 60)

    broker = TigerBroker(
        credentials_path=CREDENTIALS_PATH,
        account_id=ACCOUNT_ID,
        env="PROD",
    )

    try:
        logger.info("Connecting to Tiger broker...")
        await broker.connect()
        logger.info("Connected!")

        # Query account
        logger.info("Querying account info...")
        account = await broker.get_account(ACCOUNT_ID)
        logger.info(f"Account: {account.account_id}")
        logger.info(f"  Cash: ${account.cash:,.2f}")
        logger.info(f"  Buying Power: ${account.buying_power:,.2f}")
        logger.info(f"  Total Equity: ${account.total_equity:,.2f}")
        logger.info(f"  Margin Used: ${account.margin_used:,.2f}")

        # Query positions
        logger.info("Querying positions...")
        positions = await broker.get_positions(ACCOUNT_ID)
        if positions:
            logger.info(f"Found {len(positions)} positions:")
            for p in positions:
                logger.info(
                    f"  {p.symbol}: {p.quantity} shares @ "
                    f"${p.avg_cost:.2f} (value: ${p.market_value:,.2f})"
                )
        else:
            logger.info("No positions")

        return True

    except Exception as e:
        logger.error(f"Broker connection test failed: {e}", exc_info=True)
        return False
    finally:
        await broker.disconnect()
        logger.info("TigerBroker disconnected")


async def main():
    """Run all tests."""
    logger.info("Tiger Trading Live Test")
    logger.info(f"Credentials: {CREDENTIALS_PATH}")
    logger.info(f"Account: {ACCOUNT_ID}")
    logger.info(f"Time: {datetime.now()}")
    logger.info("")

    results = {}

    # Test 1: Broker connection
    results["broker"] = await test_broker_connection()
    logger.info("")

    # Test 2: Market data
    results["market_data"] = await test_market_data()
    logger.info("")

    # Summary
    logger.info("=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)
    for test, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"  {test}: {status}")

    all_passed = all(results.values())
    logger.info("")
    logger.info(f"Overall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
