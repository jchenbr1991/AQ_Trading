# backend/src/strategies/registry.py
import importlib
import logging
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from src.strategies.base import Strategy
    from src.core.portfolio import PortfolioManager

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """
    Loads and manages strategy instances from config file.

    Config format (strategies.yaml):
        strategies:
          - name: momentum_v1
            class: src.strategies.examples.momentum.MomentumStrategy
            account_id: "ACC001"
            symbols: ["AAPL", "TSLA"]
            params:
              lookback_period: 20
            enabled: true
    """

    def __init__(self, config_path: str, portfolio: "PortfolioManager"):
        self._config_path = config_path
        self._portfolio = portfolio
        self._strategies: dict[str, "Strategy"] = {}
        self._account_ids: dict[str, str] = {}  # strategy_name -> account_id

    async def load_strategies(self) -> None:
        """Load enabled strategies from config file."""
        with open(self._config_path, "r") as f:
            config = yaml.safe_load(f)

        for entry in config.get("strategies", []):
            if not entry.get("enabled", True):
                logger.info(f"Skipping disabled strategy: {entry['name']}")
                continue

            try:
                strategy = self._instantiate_strategy(entry)
                self._strategies[entry["name"]] = strategy
                self._account_ids[entry["name"]] = entry["account_id"]
                await strategy.on_start()
                logger.info(f"Loaded strategy: {entry['name']}")
            except Exception as e:
                logger.error(f"Failed to load strategy {entry['name']}: {e}")
                raise

    def _instantiate_strategy(self, entry: dict) -> "Strategy":
        """Import class and instantiate with params."""
        class_path = entry["class"]
        module_path, class_name = class_path.rsplit(".", 1)

        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)

        params = entry.get("params", {})
        return cls(
            name=entry["name"],
            symbols=entry["symbols"],
            **params,
        )

    def get_strategy(self, name: str) -> "Strategy | None":
        """Get strategy by name."""
        return self._strategies.get(name)

    def get_account_id(self, strategy_name: str) -> str | None:
        """Get account ID for a strategy."""
        return self._account_ids.get(strategy_name)

    def all_strategies(self) -> list["Strategy"]:
        """Get all loaded strategies."""
        return list(self._strategies.values())

    async def shutdown(self) -> None:
        """Stop all strategies gracefully."""
        for name, strategy in self._strategies.items():
            try:
                await strategy.on_stop()
                logger.info(f"Stopped strategy: {name}")
            except Exception as e:
                logger.error(f"Error stopping strategy {name}: {e}")
