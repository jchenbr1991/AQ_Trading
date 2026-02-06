# backend/tests/broker/test_config.py
"""Tests for broker configuration."""

import os
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


# ---------------------------------------------------------------------------
# T023: Tiger config fields
# ---------------------------------------------------------------------------


class TestTigerConfigFields:
    """Tests for parsing Tiger broker fields from YAML."""

    def test_load_tiger_broker_config(self):
        """from_yaml parses broker.tiger section fields."""
        yaml_content = """
broker:
  type: "tiger"
  tiger:
    credentials_path: "config/brokers/tiger_creds.json"
    account_id: "DU12345"
    env: "SANDBOX"
    max_reconnect_attempts: 5
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            config = BrokerConfig.from_yaml(f.name)

        assert config.broker_type == "tiger"
        assert config.tiger_credentials_path == "config/brokers/tiger_creds.json"
        assert config.tiger_account_id == "DU12345"
        assert config.tiger_env == "SANDBOX"
        assert config.tiger_max_reconnect_attempts == 5

    def test_tiger_defaults_when_section_missing(self):
        """Tiger fields use defaults when tiger section is absent."""
        yaml_content = """
broker:
  type: "paper"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            config = BrokerConfig.from_yaml(f.name)

        assert config.tiger_credentials_path == ""
        assert config.tiger_account_id == ""
        assert config.tiger_env == "PROD"
        assert config.tiger_max_reconnect_attempts == 3


# ---------------------------------------------------------------------------
# T024: load_broker("tiger")
# ---------------------------------------------------------------------------


class TestLoadTigerBroker:
    """Tests for load_broker factory creating TigerBroker."""

    def test_load_broker_tiger_returns_tiger_broker(self, tmp_path):
        """load_broker creates a TigerBroker with correct params."""
        creds_file = tmp_path / "tiger_creds.props"
        creds_file.write_text("tiger_id=TEST\naccount=TEST123\n")
        os.chmod(str(creds_file), 0o600)

        yaml_content = f"""
broker:
  type: "tiger"
  tiger:
    credentials_path: "{creds_file}"
    account_id: "DU99999"
    env: "SANDBOX"
    max_reconnect_attempts: 7
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            broker = load_broker(f.name)

        from src.broker.tiger_broker import TigerBroker

        assert isinstance(broker, TigerBroker)
        assert broker._credentials_path == str(creds_file)
        assert broker._account_id == "DU99999"
        assert broker._env == "SANDBOX"
        assert broker._max_reconnect_attempts == 7

    def test_load_broker_paper_still_works(self):
        """Regression: load_broker('paper') still returns PaperBroker."""
        yaml_content = """
broker:
  type: "paper"
  paper:
    fill_delay: 0.02
    slippage_bps: 3
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            broker = load_broker(f.name)

        from src.broker.paper_broker import PaperBroker

        assert isinstance(broker, PaperBroker)


# ---------------------------------------------------------------------------
# T025: Invalid credentials path
# ---------------------------------------------------------------------------


class TestTigerInvalidCredentials:
    """Tests for load_broker with invalid Tiger credentials."""

    def test_load_broker_tiger_invalid_credentials_path(self):
        """load_broker raises ValueError when credentials file doesn't exist."""
        yaml_content = """
broker:
  type: "tiger"
  tiger:
    credentials_path: "/nonexistent/path/tiger_creds.json"
    account_id: "DU12345"
    env: "SANDBOX"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            with pytest.raises(ValueError, match="Credentials file not found"):
                load_broker(f.name)
