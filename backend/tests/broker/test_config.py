# backend/tests/broker/test_config.py
"""Tests for broker configuration."""

import tempfile

import pytest
from src.broker.config import BrokerConfig, load_broker


class TestBrokerConfig:
    def test_load_paper_broker_config(self):
        """Load paper broker from config."""
        yaml_content = """
broker:
  type: "paper"
  paper:
    fill_delay: 0.05
    slippage_bps: 10
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            config = BrokerConfig.from_yaml(f.name)

        assert config.broker_type == "paper"
        assert config.paper_fill_delay == 0.05
        assert config.paper_slippage_bps == 10

    def test_load_futu_broker_config(self):
        """Load Futu broker from config."""
        yaml_content = """
broker:
  type: "futu"
  futu:
    host: "127.0.0.1"
    port: 11111
    trade_env: "SIMULATE"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            config = BrokerConfig.from_yaml(f.name)

        assert config.broker_type == "futu"
        assert config.futu_host == "127.0.0.1"
        assert config.futu_port == 11111
        assert config.futu_trade_env == "SIMULATE"

    def test_create_paper_broker(self):
        """Factory creates PaperBroker."""
        yaml_content = """
broker:
  type: "paper"
  paper:
    fill_delay: 0.01
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            broker = load_broker(f.name)

        from src.broker.paper_broker import PaperBroker

        assert isinstance(broker, PaperBroker)

    def test_config_file_not_found(self):
        """Raises error for missing config file."""
        with pytest.raises(FileNotFoundError):
            BrokerConfig.from_yaml("/nonexistent/path.yaml")

    def test_default_values(self):
        """Config uses defaults for missing values."""
        yaml_content = """
broker:
  type: "paper"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            config = BrokerConfig.from_yaml(f.name)

        assert config.paper_fill_delay == 0.1
        assert config.paper_slippage_bps == 5
        assert config.paper_partial_fill_probability == 0.0
