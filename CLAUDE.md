# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AQ Trading - algorithmic trading system for US equities and options via Futu broker.
Python backend (FastAPI) + TypeScript frontend (React).

See `STRATEGY.md` for full architecture, component design, and development guidelines.

## Commands

### Development

```bash
# Start all services
./scripts/start_dev.sh

# Backend only
cd backend && uvicorn src.main:app --reload

# Frontend only
cd frontend && npm run dev
```

### Testing

```bash
# Backend tests
cd backend && pytest

# Single test file
cd backend && pytest tests/test_portfolio.py -v

# Frontend tests
cd frontend && npm test
```

### Database

```bash
# Run migrations
cd backend && alembic upgrade head

# Create migration
cd backend && alembic revision --autogenerate -m "description"
```

### Type Generation

```bash
# Regenerate frontend types from backend OpenAPI
cd frontend && ./scripts/generate-types.sh
```

## Critical Paths

- `strategies/live/` - Production strategies, DO NOT modify without confirmation
- `frontend/src/api/generated/` - Auto-generated, never edit manually
