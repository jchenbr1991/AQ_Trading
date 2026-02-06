# Quickstart: Tiger Trading Broker Adapter

## Prerequisites

1. **Tiger Trading Account**: Sign up at [Tiger Brokers](https://www.itigerup.com/)
2. **Tiger Developer Portal**: Register at [Tiger Open Platform](https://quant.itigerup.com/)
3. **API Credentials**: Generate RSA key pair on the developer portal

## Setup

### 1. Install the Tiger SDK

```bash
cd backend
pip install tigeropen==3.3.3
```

Or add to `pyproject.toml`:
```toml
[project.optional-dependencies]
tiger = ["tigeropen>=3.3.3,<4.0"]
```

### 2. Configure Credentials

Place your Tiger credentials file at `config/brokers/tiger_openapi_config.properties`:

```properties
tiger_id=YOUR_TIGER_ID
private_key=YOUR_RSA_PRIVATE_KEY_PEM
account=YOUR_ACCOUNT_ID
license=TBNZ
```

Set file permissions:
```bash
chmod 600 config/brokers/tiger_openapi_config.properties
```

Verify the file is gitignored:
```bash
git check-ignore config/brokers/tiger_openapi_config.properties
# Should output the path (confirming it's ignored)
```

### 3. Configure Strategy YAML

Update your strategy config to use Tiger:

```yaml
broker:
  type: "tiger"
  tiger:
    credentials_path: "config/brokers/tiger_openapi_config.properties"
    account_id: "YOUR_ACCOUNT_ID"
    env: "PROD"  # or "SANDBOX" for testing

market_data:
  source: "tiger"  # or "mock" for simulated data
```

### 4. Run with Tiger Broker

```bash
# Start with Tiger broker
cd backend
python -m src.main --config path/to/strategy.yaml
```

### 5. Switch Back to Paper

Change the strategy config:
```yaml
broker:
  type: "paper"

market_data:
  source: "mock"
```

No code changes needed.

## Verification Checklist

- [ ] `config/brokers/tiger_openapi_config.properties` exists with 0600 perms
- [ ] File is gitignored (not tracked by git)
- [ ] Tiger account has API access enabled
- [ ] Tiger account has trading permissions for target markets
- [ ] Tiger account has real-time market data entitlements (if using Tiger quotes)

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `ValueError: Credentials file not found` | Missing properties file | Create file at configured path |
| `ValueError: Credentials file permissions too open` | File perms != 0600 | `chmod 600 <path>` |
| `ApiException: rate limit error` | Too many API calls | Reduce request frequency |
| `Connection refused` | Tiger servers unreachable | Check network, firewall, VPN |
| `Invalid private key` | Malformed RSA key | Re-export from Tiger developer portal |

## Running Tests

```bash
cd backend
python -m pytest tests/broker/test_tiger_broker.py -x -q
python -m pytest tests/market_data/test_tiger_source.py -x -q
```

Tests use mocked Tiger SDK — no live credentials needed.
