from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.database import get_session
from src.db.models import Decision, Signal

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("")
async def list_signals(
    symbol: str | None = None,
    strategy: str | None = None,
    action: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    """List signals with their decisions. Filterable by symbol, strategy, and decision action."""
    query = (
        select(Signal)
        .options(selectinload(Signal.decision))
        .order_by(Signal.timestamp.desc())
        .limit(limit)
        .offset(offset)
    )

    if symbol:
        query = query.where(Signal.symbol == symbol)
    if strategy:
        query = query.where(Signal.strategy_name == strategy)
    if action:
        query = query.join(Decision).where(Decision.action == action)

    result = await session.execute(query)
    signals = result.scalars().all()

    items = []
    for sig in signals:
        decision = sig.decision

        items.append({
            "id": sig.id,
            "timestamp": sig.timestamp.isoformat(),
            "strategy_name": sig.strategy_name,
            "symbol": sig.symbol.value,
            "direction": sig.direction.value,
            "strength": sig.strength,
            "reasoning": sig.reasoning,
            "decision": {
                "action": decision.action.value,
                "reasoning": decision.decision_reasoning,
                "risk_evaluation": decision.risk_evaluation,
                "stop_price": decision.stop_price,
                "target_price": decision.target_price,
            } if decision else None,
        })

    return {"signals": items}
