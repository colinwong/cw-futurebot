# cw-futurebot

Futures trading algo bot for **ES** (S&P 500 E-mini) and **NQ** (Nasdaq 100 E-mini) via Interactive Brokers.

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+ / FastAPI |
| Frontend | Next.js 15 / TradingView Lightweight Charts |
| Database | PostgreSQL 16 |
| Broker | Interactive Brokers (ib_insync) |
| News | Finnhub + Claude API for analysis |
| Alerts | Telegram Bot |

## Ports

| Service | Port |
|---------|------|
| Backend API | 8002 |
| Frontend | 3002 |
| PostgreSQL | 5434 |
| IB Gateway API | 4002 |

---

## Local Development Setup

### Prerequisites

- Python 3.12+
- Node.js 22+
- Docker (for PostgreSQL)
- IB Trader Workstation (TWS) or IB Gateway running locally

### 1. Start PostgreSQL

```bash
docker compose -f docker/docker-compose.dev.yml up -d
```

### 2. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Create `backend/.env` from the example and fill in your keys:

```bash
cp .env.example .env
```

Required env vars for local dev:
- `DATABASE_URL` — defaults to `postgresql+asyncpg://futurebot:futurebot@localhost:5434/futurebot`
- `IB_HOST` / `IB_PORT` — defaults to `127.0.0.1:4002` (IB Gateway) or use `7497` for TWS
- `FINNHUB_API_KEY` — get one at [finnhub.io](https://finnhub.io/)
- `ANTHROPIC_API_KEY` — for Claude-powered news analysis
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — create via [@BotFather](https://t.me/BotFather)

Run migrations and start the server:

```bash
alembic upgrade head
uvicorn src.main:app --reload --port 8002
```

API docs at http://localhost:8002/docs

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

UI at http://localhost:3002

### 4. IB Gateway / TWS

The bot connects to IB Gateway (or TWS) for market data and order execution. For local dev:

1. Download and install [IB Gateway](https://www.interactivebrokers.com/en/trading/ibgateway-stable.php) or TWS
2. Log in with your IB credentials
3. Enable API connections: Configure > Settings > API > Enable ActiveX and Socket Clients
4. Set the socket port to `4002` (Gateway default) or `7497` (TWS default)
5. Update `IB_PORT` in your `.env` if using TWS

Use a **paper trading** account during development.

---

## Production Deployment (VPS)

All services run in Docker Compose on a single VPS.

### 1. Provision a VPS

- Ubuntu 22.04+ with Docker and Docker Compose installed
- Minimum 2 vCPU / 4GB RAM recommended
- Open ports: 3002 (frontend), 8002 (API) — or put behind a reverse proxy
- Port 5900 exposed only for VNC access to IB Gateway re-authentication

### 2. Configure environment

Create `.env` at the project root:

```bash
cp .env.example .env
```

Fill in all values:

```env
IB_USERNAME=your_ib_username
IB_PASSWORD=your_ib_password
IB_TRADING_MODE=paper          # or "live"
IB_ACCOUNT=your_account_id

FINNHUB_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
NEWS_ANALYSIS_MODEL=claude-sonnet-4-6

TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 3. Launch

```bash
docker compose -f docker/docker-compose.yml up -d
```

This starts:
- **ib-gateway** — headless IB Gateway via [gnzsnz/ib-gateway](https://github.com/gnzsnz/ib-gateway) Docker image
- **postgres** — PostgreSQL 16 with persistent volume
- **backend** — FastAPI app, connects to IB Gateway and PostgreSQL
- **frontend** — Next.js app

### 4. Run migrations

```bash
docker compose -f docker/docker-compose.yml exec backend alembic upgrade head
```

### 5. Verify

```bash
# Check all containers are running
docker compose -f docker/docker-compose.yml ps

# Check backend health
curl http://localhost:8002/health

# Check logs
docker compose -f docker/docker-compose.yml logs -f backend
```

### IB Gateway re-authentication

IB Gateway requires manual re-authentication approximately every 1-2 weeks. When it expires:

1. Connect to VNC on port 5900 (e.g., `vnc://your-vps-ip:5900`)
2. Complete the login/2FA flow in the IB Gateway UI
3. The bot will automatically reconnect and run reconciliation

The bot sends a Telegram alert when the IB connection drops, so you'll know when re-authentication is needed.

### Container restart policy

All containers use `restart: unless-stopped`. After a VPS reboot:
- Containers auto-restart
- Backend runs startup reconciliation (compares DB positions vs IB)
- Missing protective orders are re-placed automatically
- Telegram alert sent with reconciliation results

---

## Architecture

```
MarketSnapshot → Signal → Decision → Order → Fill → TradeOutcome
```

Every trade decision is persisted with full context: what the bot saw (market snapshot, indicators), why it acted (strategy reasoning, risk evaluation), and what happened (order fills, P&L). This enables post-hoc analysis of every decision.

### Risk protection

- Every position has broker-side bracket orders (stop-loss + profit target) that execute even if the bot is completely offline
- Startup reconciliation compares DB state vs broker state and flags discrepancies
- Periodic reconciliation runs every 5 minutes during operation
- Telegram alerts on: trade executions, connection loss, reconciliation discrepancies

### Key directories

```
backend/src/
├── broker/       # Abstract broker interface + IB implementation
├── data/         # Market data interface + IB streaming
├── news/         # Pluggable news providers (Finnhub) + Claude analyzer
├── strategy/     # Strategy framework + example strategy
├── engine/       # Decision engine, risk manager, reconciliation, executor
├── telegram/     # Telegram bot alerts + commands
├── api/routes/   # REST + WebSocket endpoints
└── db/           # SQLAlchemy models + Alembic migrations

frontend/src/
├── components/   # Chart, trading, signals, news, layout components
├── hooks/        # useWebSocket, useMarketData, useOrders
├── lib/          # API client, shared types
└── app/          # Next.js pages (terminal, trades, signals, settings)
```
