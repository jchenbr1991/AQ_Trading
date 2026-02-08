#!/usr/bin/env python3
"""Live test script for Futu (moomoo) broker adapter.

Connects to a locally running OpenD gateway and tests:
1. Connection to OpenD
2. Account info query
3. Position query
4. Simulated order placement (SIMULATE env only)

Usage:
    cd backend
    python scripts/test_futu_live.py
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)

from src.broker.futu_broker import FutuBroker  # noqa: E402
from src.orders.models import Order, OrderStatus  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

FUTU_HOST = os.environ.get("FUTU_HOST", "127.0.0.1")
FUTU_PORT = int(os.environ.get("FUTU_PORT", "11111"))
TRADE_ENV = os.environ.get("FUTU_TRADE_ENV", "SIMULATE")


async def test_broker_connection():
    """Test FutuBroker connection and account query."""
    logger.info("=" * 60)
    logger.info("Testing FutuBroker - Connection & Account")
    logger.info("=" * 60)

    broker = FutuBroker(
        host=FUTU_HOST,
        port=FUTU_PORT,
        trade_env=TRADE_ENV,
    )

    try:
        logger.info(f"Connecting to OpenD at {FUTU_HOST}:{FUTU_PORT} (env={TRADE_ENV})...")
        await broker.connect()
        logger.info("Connected!")

        # Query account
        logger.info("Querying account info...")
        account = await broker.get_account("")
        logger.info(f"Account: {account.account_id}")
        logger.info(f"  Cash: ${account.cash:,.2f}")
        logger.info(f"  Buying Power: ${account.buying_power:,.2f}")
        logger.info(f"  Total Equity: ${account.total_equity:,.2f}")
        logger.info(f"  Margin Used: ${account.margin_used:,.2f}")

        # Query positions
        logger.info("Querying positions...")
        positions = await broker.get_positions("")
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
        logger.info("FutuBroker disconnected")


async def test_simulated_order():
    """Test placing a simulated order (SIMULATE env only)."""
    if TRADE_ENV != "SIMULATE":
        logger.info("Skipping simulated order test (not in SIMULATE env)")
        return True

    logger.info("=" * 60)
    logger.info("Testing FutuBroker - Simulated Order")
    logger.info("=" * 60)

    broker = FutuBroker(
        host=FUTU_HOST,
        port=FUTU_PORT,
        trade_env="SIMULATE",
    )

    try:
        await broker.connect()

        # Subscribe to fills
        fills_received = []
        broker.subscribe_fills(lambda fill: fills_received.append(fill))

        # Place a small limit order
        order = Order(
            order_id="live-test-001",
            broker_order_id=None,
            strategy_id="live-test",
            symbol="AAPL",
            side="buy",
            quantity=1,
            order_type="limit",
            limit_price=Decimal("100.00"),  # Far below market, won't fill
            status=OrderStatus.PENDING,
        )

        logger.info(
            f"Placing test order: {order.side} {order.quantity} {order.symbol} @ ${order.limit_price}"
        )
        broker_order_id = await broker.submit_order(order)
        logger.info(f"Order placed: broker_order_id={broker_order_id}")

        # Check status
        status = await broker.get_order_status(broker_order_id)
        logger.info(f"Order status: {status}")

        # Cancel the order
        logger.info("Cancelling test order...")
        cancelled = await broker.cancel_order(broker_order_id)
        logger.info(f"Cancel result: {cancelled}")

        # Verify cancelled
        await asyncio.sleep(1)
        status = await broker.get_order_status(broker_order_id)
        logger.info(f"Final order status: {status}")

        return True

    except Exception as e:
        logger.error(f"Simulated order test failed: {e}", exc_info=True)
        return False
    finally:
        await broker.disconnect()
        logger.info("FutuBroker disconnected")


async def main():
    """Run all tests."""
    logger.info("Futu (moomoo) Broker Live Test")
    logger.info(f"OpenD: {FUTU_HOST}:{FUTU_PORT}")
    logger.info(f"Trade Env: {TRADE_ENV}")
    logger.info(f"Time: {datetime.now()}")
    logger.info("")

    results = {}

    # Test 1: Broker connection + account/positions
    results["broker"] = await test_broker_connection()
    logger.info("")

    # Test 2: Simulated order
    results["simulated_order"] = await test_simulated_order()
    logger.info("")

    # Summary
    logger.info("=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)
    for test, passed in results.items():
        status = "PASS" if passed else "FAIL"
        logger.info(f"  {test}: {status}")

    all_passed = all(results.values())
    logger.info("")
    logger.info(f"Overall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
