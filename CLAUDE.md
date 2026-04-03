# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

cw-futurebot — Futures trading algo bot for ES (S&P 500 E-mini) and NQ (Nasdaq 100 E-mini) via Interactive Brokers. Python/FastAPI backend, Next.js 15 frontend, PostgreSQL, Telegram bot.

## Architecture

### Core Design Principles
1. **Full decision audit trail**: Every signal, decision, and trade outcome is persisted with complete context. Chain: `MarketSnapshot → Signal → Decision → Order → Fill → TradeOutcome`
2. **Crash resilience**: Broker-side bracket orders (stop + target) protect positions even if the bot/PC/internet dies. Startup reconciliation compares DB vs broker state.

### Backend (`backend/src/`)
- **FastAPI** app on port **8002** with async SQLAlchemy + PostgreSQL (port **5434**)
- `broker/` — Abstract broker interface + IB implementation (`ib_insync`). Bracket orders as OCA groups.
- `data/` — Abstract market data interface + IB streaming implementation
- `news/` — Pluggable news providers (Finnhub default) + Claude API analyzer for relevance/sentiment/impact
- `strategy/` — Abstract strategy base. Strategies return `StrategySignal` with structured reasoning.
- `engine/` — Decision engine (audit bridge), risk manager (bracket enforcement, position limits, daily loss), reconciliation (DB vs broker), hybrid executor (polling + event-driven)
- `telegram/` — Bot alerts + commands (/status, /positions, /pnl, /stop)
- `api/routes/` — REST + WebSocket endpoints for UI

### Frontend (`frontend/src/`)
- **Next.js 15** on port **3002** with TradingView Lightweight Charts
- Side-by-side ES + NQ charts with indicators, algo decision markers, news event markers
- Manual trading: bracket order entry, position management, order modification
- Real-time via WebSocket: candles, positions, orders, signals, news, account updates

### Database Models (`backend/src/db/models.py`)
Key tables: `market_snapshots`, `news_events`, `signals`, `decisions`, `orders`, `fills`, `positions`, `trade_outcomes`, `strategy_logs`, `protective_orders`, `system_events`

## Commands

### Backend
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn src.main:app --reload --port 8002    # Dev server
alembic upgrade head                          # Run migrations
alembic revision --autogenerate -m "desc"     # Create migration
ruff check src/                               # Lint
pytest                                        # Tests
```

### Frontend
```bash
cd frontend
npm install
npm run dev          # Dev server on port 3002
npm run build        # Production build
npm run lint         # Lint
```

### Docker (local dev)
```bash
docker compose -f docker/docker-compose.dev.yml up -d   # PostgreSQL only
docker compose -f docker/docker-compose.yml up -d        # Full stack (production)
```

## Ports
| Service | Port |
|---------|------|
| Backend API | 8002 |
| Frontend | 3002 |
| PostgreSQL | 5434 |
| IB Gateway | 4002 |

These avoid conflicts with cw-tradebot (8000/5173/5432) and cw-tradebot2 (8000/5173/5433).

## Key Patterns
- **News analysis**: Finnhub → Claude API (tool_use for structured output) → persisted with relevance/sentiment/impact → significant events shown on chart
- **Risk enforcement**: No position opened without broker-side bracket order (stop + target)
- **Reconciliation**: Runs at startup + every 5 minutes. Compares DB positions vs IB positions, flags discrepancies, re-places missing protective orders
- **Audit trail queries**: `/api/trades/{id}/audit` returns full chain from market snapshot through outcome
