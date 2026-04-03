from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.database import get_session
from src.db.models import Position

router = APIRouter(prefix="/api/positions", tags=["positions"])


@router.get("")
async def list_positions(
    open_only: bool = True,
    session: AsyncSession = Depends(get_session),
):
    """List current positions."""
    query = (
        select(Position)
        .options(selectinload(Position.protective_orders))
        .order_by(Position.entry_timestamp.desc())
    )
    if open_only:
        query = query.where(Position.is_open.is_(True))

    result = await session.execute(query)
    positions = result.scalars().all()

    items = []
    for pos in positions:
        protective = pos.protective_orders[0] if pos.protective_orders else None

        items.append({
            "id": pos.id,
            "symbol": pos.symbol.value,
            "direction": pos.direction.value,
            "quantity": pos.quantity,
            "entry_price": pos.entry_price,
            "entry_timestamp": pos.entry_timestamp.isoformat(),
            "exit_price": pos.exit_price,
            "exit_timestamp": pos.exit_timestamp.isoformat() if pos.exit_timestamp else None,
            "is_open": pos.is_open,
            "protective_order": {
                "status": protective.status.value,
                "verified_at": protective.verified_at.isoformat() if protective.verified_at else None,
            } if protective else None,
        })

    return {"positions": items}
