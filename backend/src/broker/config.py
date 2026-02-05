# backend/src/broker/config.py
"""Broker configuration loading."""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class BrokerConfig:
    """Configuration for broker selection and settings."""

    broker_type: str

    # Paper broker settings (matching PaperBroker.__init__ params)
    paper_fill_delay: float = 0.1
    paper_slippage_bps: int = 5
    paper_partial_fill_probability: float = 0.0

    # Futu broker settings
    futu_host: str = "127.0.0.1"
    futu_port: int = 11111
    futu_trade_env: str = "SIMULATE"

    # Tiger broker settings
    tiger_credentials_path: str = ""
    tiger_account_id: str = ""
    tiger_env: str = "PROD"
    tiger_max_reconnect_attempts: int = 3

    @classmethod
    def from_yaml(cls, path: str) -> "BrokerConfig":
        """Load broker config from YAML file."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(file_path) as f:
            data = yaml.safe_load(f)

        broker_data = data.get("broker", {})
        paper_data = broker_data.get("paper", {})
        futu_data = broker_data.get("futu", {})
        tiger_data = broker_data.get("tiger", {})

        return cls(
            broker_type=broker_data.get("type", "paper"),
            paper_fill_delay=paper_data.get("fill_delay", 0.1),
            paper_slippage_bps=paper_data.get("slippage_bps", 5),
            paper_partial_fill_probability=paper_data.get("partial_fill_probability", 0.0),
            futu_host=futu_data.get("host", "127.0.0.1"),
            futu_port=futu_data.get("port", 11111),
            futu_trade_env=futu_data.get("trade_env", "SIMULATE"),
            tiger_credentials_path=tiger_data.get("credentials_path", ""),
            tiger_account_id=tiger_data.get("account_id", ""),
            tiger_env=tiger_data.get("env", "PROD"),
            tiger_max_reconnect_attempts=tiger_data.get("max_reconnect_attempts", 3),
        )


def load_broker(config_path: str):
    """Factory function to create broker from config file."""
    from src.broker.paper_broker import PaperBroker

    config = BrokerConfig.from_yaml(config_path)

    if config.broker_type == "paper":
        return PaperBroker(
            fill_delay=config.paper_fill_delay,
            slippage_bps=config.paper_slippage_bps,
            partial_fill_probability=config.paper_partial_fill_probability,
        )
    elif config.broker_type == "tiger":
        from src.broker.tiger_broker import TigerBroker

        return TigerBroker(
            credentials_path=config.tiger_credentials_path,
            account_id=config.tiger_account_id,
            env=config.tiger_env,
            max_reconnect_attempts=config.tiger_max_reconnect_attempts,
        )
    elif config.broker_type == "futu":
        raise NotImplementedError("FutuBroker not yet implemented")
    else:
        raise ValueError(f"Unknown broker type: {config.broker_type}")
