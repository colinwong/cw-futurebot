from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.database import get_session
from src.db.models import Order, Position, ProtectiveOrder

router = APIRouter(prefix="/api/positions", tags=["positions"])


@router.get("")
async def list_positions(
    open_only: bool = True,
    session: AsyncSession = Depends(get_session),
):
    """List current positions with protective order prices."""
    query = (
        select(Position)
        .options(
            selectinload(Position.protective_orders)
            .selectinload(ProtectiveOrder.stop_order),
            selectinload(Position.protective_orders)
            .selectinload(ProtectiveOrder.target_order),
        )
        .order_by(Position.entry_timestamp.desc())
    )
    if open_only:
        query = query.where(Position.is_open.is_(True))

    result = await session.execute(query)
    positions = result.scalars().all()

    items = []
    for pos in positions:
        protective = pos.protective_orders[0] if pos.protective_orders else None
        stop_price = None
        target_price = None
        if protective:
            if protective.stop_order:
                stop_price = protective.stop_order.stop_price
            if protective.target_order:
                target_price = protective.target_order.limit_price

        items.append({
            "id": pos.id,
            "symbol": pos.symbol.value,
            "direction": pos.direction.value,
            "quantity": pos.quantity,
            "entry_price": pos.entry_price,
            "stop_price": stop_price,
            "target_price": target_price,
            "stop_ib_order_id": protective.stop_ib_order_id if protective else None,
            "target_ib_order_id": protective.target_ib_order_id if protective else None,
            "entry_timestamp": pos.entry_timestamp.isoformat(),
            "exit_price": pos.exit_price,
            "exit_timestamp": pos.exit_timestamp.isoformat() if pos.exit_timestamp else None,
            "is_open": pos.is_open,
            "protective_status": protective.status.value if protective else None,
        })

    return {"positions": items}
