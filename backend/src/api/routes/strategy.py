from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.db.models import StrategyLog

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


@router.get("/logs")
async def get_strategy_logs(
    strategy_name: str | None = None,
    symbol: str | None = None,
    limit: int = Query(50, le=200),
    session: AsyncSession = Depends(get_session),
):
    """Get strategy evaluation logs."""
    query = select(StrategyLog).order_by(StrategyLog.timestamp.desc()).limit(limit)

    if strategy_name:
        query = query.where(StrategyLog.strategy_name == strategy_name)
    if symbol:
        query = query.where(StrategyLog.symbol == symbol)

    result = await session.execute(query)
    logs = result.scalars().all()

    return {
        "logs": [
            {
                "id": log.id,
                "timestamp": log.timestamp.isoformat(),
                "strategy_name": log.strategy_name,
                "symbol": log.symbol.value,
                "state": log.state,
            }
            for log in logs
        ]
    }
