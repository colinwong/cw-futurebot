from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.broker.base import BaseBroker
from src.db.database import get_session
from src.db.models import (
    DirectionEnum,
    Order,
    OrderSideEnum,
    OrderStatusEnum,
    OrderTypeEnum,
    Position,
    ProtectiveOrder,
    ProtectiveOrderStatusEnum,
    SymbolEnum,
)

router = APIRouter(prefix="/api/orders", tags=["orders"])

# Broker instance set during app startup via set_broker()
_broker: BaseBroker | None = None


def set_broker(broker: BaseBroker) -> None:
    global _broker
    _broker = broker


def _require_broker() -> BaseBroker:
    if not _broker:
        raise HTTPException(status_code=503, detail="Broker not connected")
    return _broker


async def _get_order_or_404(session: AsyncSession, order_id: int) -> Order:
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


class BracketOrderRequest(BaseModel):
    symbol: SymbolEnum
    side: OrderSideEnum
    quantity: int = 1
    order_type: OrderTypeEnum = OrderTypeEnum.MARKET
    entry_price: float | None = None
    stop_price: float
    target_price: float


class ModifyOrderRequest(BaseModel):
    limit_price: float | None = None
    stop_price: float | None = None
    quantity: int | None = None


@router.get("")
async def list_orders(
    status: OrderStatusEnum | None = None,
    session: AsyncSession = Depends(get_session),
):
    """List orders, optionally filtered by status."""
    query = select(Order).order_by(Order.timestamp.desc()).limit(100)
    if status:
        query = query.where(Order.status == status)

    result = await session.execute(query)
    orders = result.scalars().all()

    return {
        "orders": [
            {
                "id": o.id,
                "symbol": o.symbol.value,
                "side": o.side.value,
                "order_type": o.order_type.value,
                "quantity": o.quantity,
                "limit_price": o.limit_price,
                "stop_price": o.stop_price,
                "status": o.status.value,
                "ib_order_id": o.ib_order_id,
                "is_manual": o.is_manual,
                "timestamp": o.timestamp.isoformat(),
            }
            for o in orders
        ]
    }


@router.post("/bracket")
async def place_bracket_order(
    req: BracketOrderRequest,
    session: AsyncSession = Depends(get_session),
):
    """Place a manual bracket order (entry + stop + target)."""
    broker = _require_broker()

    direction = DirectionEnum.LONG if req.side == OrderSideEnum.BUY else DirectionEnum.SHORT

    # Risk check: block if there's already an open position on this symbol
    existing = await session.execute(
        select(Position).where(
            Position.symbol == req.symbol,
            Position.is_open.is_(True),
        )
    )
    existing_pos = existing.scalars().first()
    if existing_pos:
        if existing_pos.direction == direction:
            raise HTTPException(
                status_code=400,
                detail=f"Already have an open {direction.value} position in {req.symbol.value}. Close it first.",
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Conflicting {existing_pos.direction.value} position already open in {req.symbol.value}. Close it before opening a {direction.value}.",
            )

    result = await broker.place_bracket_order(
        symbol=req.symbol,
        direction=direction,
        quantity=req.quantity,
        entry_order_type=req.order_type.value,
        entry_price=req.entry_price,
        stop_price=req.stop_price,
        target_price=req.target_price,
    )

    exit_side = OrderSideEnum.SELL if req.side == OrderSideEnum.BUY else OrderSideEnum.BUY

    entry_order = Order(
        symbol=req.symbol,
        side=req.side,
        order_type=req.order_type,
        quantity=req.quantity,
        limit_price=req.entry_price,
        ib_order_id=result.entry_order_id,
        status=OrderStatusEnum.SUBMITTED,
        is_manual=True,
    )
    stop_order = Order(
        symbol=req.symbol,
        side=exit_side,
        order_type=OrderTypeEnum.STOP,
        quantity=req.quantity,
        stop_price=req.stop_price,
        ib_order_id=result.stop_order_id,
        status=OrderStatusEnum.SUBMITTED,
        is_manual=True,
    )
    target_order = Order(
        symbol=req.symbol,
        side=exit_side,
        order_type=OrderTypeEnum.LIMIT,
        quantity=req.quantity,
        limit_price=req.target_price,
        ib_order_id=result.target_order_id,
        status=OrderStatusEnum.SUBMITTED,
        is_manual=True,
    )

    session.add_all([entry_order, stop_order, target_order])
    await session.flush()

    # Create position record for the trade
    position = Position(
        symbol=req.symbol,
        direction=direction,
        quantity=req.quantity,
        entry_price=req.entry_price or 0,  # 0 for market orders, updated on fill
        entry_timestamp=datetime.now(timezone.utc),
        is_open=True,
    )
    session.add(position)
    await session.flush()

    # Track protective orders
    protective = ProtectiveOrder(
        position_id=position.id,
        stop_order_id=stop_order.id,
        target_order_id=target_order.id,
        stop_ib_order_id=result.stop_order_id,
        target_ib_order_id=result.target_order_id,
        verified_at=datetime.now(timezone.utc),
    )
    session.add(protective)
    await session.commit()

    return {
        "entry_order_id": result.entry_order_id,
        "stop_order_id": result.stop_order_id,
        "target_order_id": result.target_order_id,
        "position_id": position.id,
    }


@router.put("/{order_id}")
async def modify_order(
    order_id: int,
    req: ModifyOrderRequest,
    session: AsyncSession = Depends(get_session),
):
    """Modify an existing order."""
    broker = _require_broker()
    order = await _get_order_or_404(session, order_id)

    await broker.modify_order(
        order_id=order.ib_order_id,
        limit_price=req.limit_price,
        stop_price=req.stop_price,
        quantity=req.quantity,
    )

    if req.limit_price is not None:
        order.limit_price = req.limit_price
    if req.stop_price is not None:
        order.stop_price = req.stop_price
    if req.quantity is not None:
        order.quantity = req.quantity
    await session.commit()

    return {"status": "modified"}


@router.delete("/{order_id}")
async def cancel_order(
    order_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Cancel an order."""
    broker = _require_broker()
    order = await _get_order_or_404(session, order_id)

    await broker.cancel_order(order.ib_order_id)
    order.status = OrderStatusEnum.CANCELLED
    await session.commit()

    return {"status": "cancelled"}


@router.post("/close-position")
async def close_position(
    symbol: SymbolEnum,
    position_id: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Close an open position at market. Cancels protective orders first."""
    broker = _require_broker()

    if position_id:
        result = await session.execute(
            select(Position).where(Position.id == position_id, Position.is_open.is_(True))
        )
    else:
        result = await session.execute(
            select(Position).where(Position.symbol == symbol, Position.is_open.is_(True))
        )
    position = result.scalars().first()
    if not position:
        raise HTTPException(status_code=404, detail="No open position found")

    # Cancel protective orders at IB first
    prot_result = await session.execute(
        select(ProtectiveOrder).where(
            ProtectiveOrder.position_id == position.id,
            ProtectiveOrder.status == ProtectiveOrderStatusEnum.ACTIVE,
        )
    )
    protective = prot_result.scalars().first()
    if protective:
        for ib_id in [protective.stop_ib_order_id, protective.target_ib_order_id]:
            if ib_id:
                try:
                    await broker.cancel_order(ib_id)
                except Exception:
                    pass  # Order may already be filled/cancelled
        protective.status = ProtectiveOrderStatusEnum.CANCELLED

        # Cancel the orders in DB too
        for order_id in [protective.stop_order_id, protective.target_order_id]:
            if order_id:
                ord_result = await session.execute(select(Order).where(Order.id == order_id))
                order = ord_result.scalars().first()
                if order and order.status == OrderStatusEnum.SUBMITTED:
                    order.status = OrderStatusEnum.CANCELLED

    # Place the close order
    exit_side = "SELL" if position.direction == DirectionEnum.LONG else "BUY"
    order_id = await broker.place_order(
        symbol=symbol,
        side=exit_side,
        order_type="MARKET",
        quantity=position.quantity,
    )

    # Mark position as closed
    position.is_open = False
    position.exit_timestamp = datetime.now(timezone.utc)
    await session.commit()

    return {"order_id": order_id, "action": f"Closing {position.direction.value} {symbol.value} at market"}
