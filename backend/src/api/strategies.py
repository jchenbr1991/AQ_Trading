# backend/src/api/strategies.py
"""Strategy management API endpoints for paper/live trading modes.

Implements T041: Strategy start/stop API endpoints for paper mode.
Implements T046: Extend API to support live mode with broker connection verification.
Supports FR-021: Same logic for backtest/paper/live modes.
"""

import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.broker.live_broker import (
    BrokerConnectionError,
    LiveBroker,
    RiskLimits,
)
from src.broker.paper_broker import PaperBroker
from src.strategies.base import Strategy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class StrategyMode(str, Enum):
    """Trading mode for strategy execution."""

    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class StartStrategyRequest(BaseModel):
    """Request body for starting a strategy."""

    mode: Literal["paper", "backtest", "live"] = Field(
        ..., description="Trading mode to run the strategy in"
    )
    confirm_live: bool = Field(
        default=False,
        description="Explicit confirmation for live trading (required when mode=live)",
    )


class StrategyStatus(str, Enum):
    """Current status of a strategy."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class StrategyStateResponse(BaseModel):
    """Response containing strategy state information."""

    name: str
    status: StrategyStatus
    mode: str | None = None
    started_at: str | None = None
    account_id: str | None = None
    symbols: list[str] = []
    error: str | None = None


# In-memory storage for running strategies (MVP - use database in production)
_running_strategies: dict[str, dict] = {}


def get_running_strategies() -> dict[str, dict]:
    """Get the running strategies storage. Override in tests."""
    return _running_strategies


def clear_running_strategies() -> None:
    """Clear the running strategies storage (for testing)."""
    _running_strategies.clear()


def _load_strategy_config(strategy_name: str) -> dict:
    """Load strategy configuration from YAML file.

    Args:
        strategy_name: Name of the strategy (maps to config file).

    Returns:
        Dictionary with strategy configuration.

    Raises:
        HTTPException: If config file not found.
    """
    # Map strategy name to config file
    config_path = (
        Path(__file__).parent.parent.parent / "config" / "strategies" / f"{strategy_name}.yaml"
    )

    if not config_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Strategy configuration not found: {strategy_name}",
        )

    with open(config_path) as f:
        return yaml.safe_load(f)


def _create_strategy_instance(config: dict) -> Strategy:
    """Create a strategy instance from configuration.

    Args:
        config: Strategy configuration dictionary.

    Returns:
        Instantiated Strategy object.

    Raises:
        HTTPException: If strategy class cannot be loaded.
    """
    import importlib

    strategy_config = config.get("strategy", {})
    class_path = strategy_config.get("class")

    if not class_path:
        raise HTTPException(
            status_code=400,
            detail="Strategy class not specified in configuration",
        )

    try:
        module_path, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        strategy_cls = getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to load strategy class '{class_path}': {e}",
        ) from e

    # Build strategy params
    params = {
        "name": strategy_config.get("name", "unnamed"),
        "symbols": strategy_config.get("symbols", ["AAPL"]),  # Default symbol for MVP
        "entry_threshold": strategy_config.get("entry_threshold", 0.0),
        "exit_threshold": strategy_config.get("exit_threshold", -0.02),
        "position_sizing": strategy_config.get("position_sizing", "equal_weight"),
        "position_size": strategy_config.get("position_size", 100),
    }

    # Add optional weights if present
    if "feature_weights" in strategy_config:
        params["feature_weights"] = strategy_config["feature_weights"]
    if "factor_weights" in strategy_config:
        params["factor_weights"] = strategy_config["factor_weights"]

    return strategy_cls(**params)


async def _setup_live_broker(
    strategy_name: str, mode_config: dict, confirm_live: bool
) -> LiveBroker:
    """Setup and verify live broker connection.

    T046: Live mode setup with broker connection verification and safety checks.

    Args:
        strategy_name: Name of the strategy being started.
        mode_config: Live mode configuration from strategy YAML.
        confirm_live: Whether live trading has been explicitly confirmed.

    Returns:
        Configured and connected LiveBroker instance.

    Raises:
        HTTPException: If broker setup or verification fails.
    """
    # Check confirmation requirement
    require_confirmation = mode_config.get("require_confirmation", True)
    if require_confirmation and not confirm_live:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Live trading for strategy '{strategy_name}' requires explicit confirmation. "
                "Set confirm_live=true to proceed."
            ),
        )

    # Get broker configuration
    broker_type = mode_config.get("broker", "stub")
    account_id = mode_config.get("account_id")

    if not account_id:
        raise HTTPException(
            status_code=400,
            detail=f"Live mode requires account_id to be configured for strategy '{strategy_name}'",
        )

    # Parse risk limits from config
    risk_limits_config = mode_config.get("risk_limits", {})
    risk_limits = RiskLimits.from_dict(risk_limits_config)

    # Create live broker
    broker = LiveBroker(
        broker_type=broker_type,
        account_id=account_id,
        risk_limits=risk_limits,
        require_confirmation=require_confirmation,
    )

    # Connect to broker
    try:
        await broker.connect()
    except BrokerConnectionError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to connect to broker: {e}",
        ) from e

    # Verify connection
    if mode_config.get("require_broker_connection", True):
        verification = await broker.verify_connection()
        if not verification.passed:
            await broker.disconnect()
            raise HTTPException(
                status_code=503,
                detail=f"Broker connection verification failed: {verification.message}",
            )

    # Confirm live trading if requested
    if confirm_live:
        broker.confirm_live_trading()

    logger.warning(
        f"LIVE BROKER CONNECTED for strategy '{strategy_name}': "
        f"broker={broker_type}, account={account_id}"
    )

    return broker


@router.post("/{name}/start", response_model=StrategyStateResponse)
async def start_strategy(name: str, request: StartStrategyRequest) -> StrategyStateResponse:
    """Start a strategy in the specified mode.

    Args:
        name: Strategy name (e.g., 'trend_breakout').
        request: Request body with mode specification.

    Returns:
        StrategyStateResponse with current strategy state.

    Raises:
        HTTPException: 400 if mode not enabled or strategy already running.
        HTTPException: 404 if strategy configuration not found.
    """
    running_strategies = get_running_strategies()

    # Check if strategy is already running
    if name in running_strategies:
        existing = running_strategies[name]
        if existing.get("status") == StrategyStatus.RUNNING:
            raise HTTPException(
                status_code=400,
                detail=f"Strategy '{name}' is already running in {existing.get('mode')} mode",
            )

    # Load configuration
    config = _load_strategy_config(name)
    modes_config = config.get("modes", {})

    # Validate mode is enabled
    mode_config = modes_config.get(request.mode, {})
    if request.mode != "backtest" and not mode_config.get("enabled", False):
        raise HTTPException(
            status_code=400,
            detail=f"Mode '{request.mode}' is not enabled for strategy '{name}'",
        )

    # Get account_id for the mode
    account_id = mode_config.get("account_id")
    if request.mode == "paper" and not account_id:
        account_id = "PAPER001"  # Default paper account

    try:
        # Create strategy instance
        strategy = _create_strategy_instance(config)

        # Create broker for the mode
        if request.mode == "paper":
            fill_delay = mode_config.get("fill_delay_ms", 100) / 1000.0
            slippage_bps = mode_config.get("slippage_bps", 5)
            broker = PaperBroker(
                fill_delay=fill_delay,
                slippage_bps=slippage_bps,
            )
        elif request.mode == "live":
            # T046: Live mode with broker connection verification and safety checks
            broker = await _setup_live_broker(name, mode_config, request.confirm_live)
        else:
            # Backtest mode - no broker needed, use backtest engine
            broker = None

        # Initialize strategy
        await strategy.on_start()

        # Store running strategy state
        started_at = datetime.utcnow()
        running_strategies[name] = {
            "strategy": strategy,
            "broker": broker,
            "status": StrategyStatus.RUNNING,
            "mode": request.mode,
            "started_at": started_at,
            "account_id": account_id,
            "symbols": strategy.symbols,
        }

        logger.info(f"Started strategy '{name}' in {request.mode} mode")

        return StrategyStateResponse(
            name=name,
            status=StrategyStatus.RUNNING,
            mode=request.mode,
            started_at=started_at.isoformat(),
            account_id=account_id,
            symbols=strategy.symbols,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start strategy '{name}': {e}", exc_info=True)
        running_strategies[name] = {
            "status": StrategyStatus.ERROR,
            "error": str(e),
        }
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start strategy: {e}",
        ) from e


@router.post("/{name}/stop", response_model=StrategyStateResponse)
async def stop_strategy(name: str) -> StrategyStateResponse:
    """Stop a running strategy.

    Args:
        name: Strategy name.

    Returns:
        StrategyStateResponse with stopped state.

    Raises:
        HTTPException: 404 if strategy is not running.
    """
    running_strategies = get_running_strategies()

    if name not in running_strategies:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy '{name}' is not running",
        )

    state = running_strategies[name]

    if state.get("status") != StrategyStatus.RUNNING:
        raise HTTPException(
            status_code=400,
            detail=f"Strategy '{name}' is not in running state (current: {state.get('status')})",
        )

    try:
        # Update status
        state["status"] = StrategyStatus.STOPPING

        # Stop the strategy
        strategy = state.get("strategy")
        if strategy:
            await strategy.on_stop()

        # T046: Disconnect live broker if applicable
        broker = state.get("broker")
        if broker and isinstance(broker, LiveBroker):
            broker.revoke_confirmation()
            await broker.disconnect()
            logger.info(f"Disconnected live broker for strategy '{name}'")

        # Remove from running strategies
        del running_strategies[name]

        logger.info(f"Stopped strategy '{name}'")

        return StrategyStateResponse(
            name=name,
            status=StrategyStatus.STOPPED,
            mode=state.get("mode"),
        )

    except Exception as e:
        logger.error(f"Error stopping strategy '{name}': {e}", exc_info=True)
        state["status"] = StrategyStatus.ERROR
        state["error"] = str(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop strategy: {e}",
        ) from e


@router.get("/{name}/status", response_model=StrategyStateResponse)
async def get_strategy_status(name: str) -> StrategyStateResponse:
    """Get the current status of a strategy.

    Args:
        name: Strategy name.

    Returns:
        StrategyStateResponse with current state.
    """
    running_strategies = get_running_strategies()

    if name not in running_strategies:
        return StrategyStateResponse(
            name=name,
            status=StrategyStatus.STOPPED,
        )

    state = running_strategies[name]

    return StrategyStateResponse(
        name=name,
        status=state.get("status", StrategyStatus.STOPPED),
        mode=state.get("mode"),
        started_at=state.get("started_at").isoformat() if state.get("started_at") else None,
        account_id=state.get("account_id"),
        symbols=state.get("symbols", []),
        error=state.get("error"),
    )


@router.get("", response_model=list[StrategyStateResponse])
async def list_strategies() -> list[StrategyStateResponse]:
    """List all strategies and their current status.

    Returns:
        List of StrategyStateResponse for all known strategies.
    """
    running_strategies = get_running_strategies()
    responses = []

    # Add running strategies
    for name, state in running_strategies.items():
        responses.append(
            StrategyStateResponse(
                name=name,
                status=state.get("status", StrategyStatus.STOPPED),
                mode=state.get("mode"),
                started_at=state.get("started_at").isoformat() if state.get("started_at") else None,
                account_id=state.get("account_id"),
                symbols=state.get("symbols", []),
                error=state.get("error"),
            )
        )

    # Discover available strategies from config files
    config_dir = Path(__file__).parent.parent.parent / "config" / "strategies"
    if config_dir.exists():
        for config_file in config_dir.glob("*.yaml"):
            strategy_name = config_file.stem
            if strategy_name not in running_strategies:
                responses.append(
                    StrategyStateResponse(
                        name=strategy_name,
                        status=StrategyStatus.STOPPED,
                    )
                )

    return responses
