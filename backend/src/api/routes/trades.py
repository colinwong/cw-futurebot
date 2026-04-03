from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.database import get_session
from src.db.models import (
    Decision,
    Fill,
    MarketSnapshot,
    Order,
    Position,
    Signal,
    TradeOutcome,
)

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("")
async def list_trades(
    symbol: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    """List trade history (closed positions with outcomes)."""
    query = (
        select(Position)
        .where(Position.is_open.is_(False))
        .options(selectinload(Position.trade_outcome))
        .order_by(Position.exit_timestamp.desc())
        .limit(limit)
        .offset(offset)
    )
    if symbol:
        query = query.where(Position.symbol == symbol)

    result = await session.execute(query)
    positions = result.scalars().all()

    trades = []
    for pos in positions:
        outcome = pos.trade_outcome

        trades.append({
            "id": pos.id,
            "symbol": pos.symbol.value,
            "direction": pos.direction.value,
            "quantity": pos.quantity,
            "entry_price": pos.entry_price,
            "exit_price": pos.exit_price,
            "entry_timestamp": pos.entry_timestamp.isoformat() if pos.entry_timestamp else None,
            "exit_timestamp": pos.exit_timestamp.isoformat() if pos.exit_timestamp else None,
            "pnl": outcome.pnl if outcome else None,
            "r_multiple": outcome.r_multiple if outcome else None,
            "hold_duration_seconds": outcome.hold_duration_seconds if outcome else None,
        })

    return {"trades": trades, "total": len(trades)}


@router.get("/{trade_id}/audit")
async def get_trade_audit(
    trade_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get full audit trail for a trade: snapshot → signal → decision → orders → fills → outcome."""
    # Get position
    pos_result = await session.execute(select(Position).where(Position.id == trade_id))
    position = pos_result.scalars().first()
    if not position:
        return {"error": "Trade not found"}

    # Get entry decision chain
    entry_chain = None
    if position.entry_decision_id:
        dec_result = await session.execute(
            select(Decision).where(Decision.id == position.entry_decision_id)
        )
        decision = dec_result.scalars().first()
        if decision:
            # Get signal
            sig_result = await session.execute(
                select(Signal).where(Signal.id == decision.signal_id)
            )
            signal = sig_result.scalars().first()

            # Get snapshot
            snapshot = None
            if signal:
                snap_result = await session.execute(
                    select(MarketSnapshot).where(MarketSnapshot.id == signal.snapshot_id)
                )
                snapshot = snap_result.scalars().first()

            # Get orders and fills
            orders_result = await session.execute(
                select(Order).where(Order.decision_id == decision.id)
            )
            orders = orders_result.scalars().all()

            order_data = []
            for order in orders:
                fills_result = await session.execute(
                    select(Fill).where(Fill.order_id == order.id)
                )
                fills = fills_result.scalars().all()
                order_data.append({
                    "id": order.id,
                    "side": order.side.value,
                    "order_type": order.order_type.value,
                    "quantity": order.quantity,
                    "limit_price": order.limit_price,
                    "stop_price": order.stop_price,
                    "status": order.status.value,
                    "ib_order_id": order.ib_order_id,
                    "fills": [
                        {
                            "fill_price": f.fill_price,
                            "quantity": f.quantity,
                            "commission": f.commission,
                            "slippage": f.slippage,
                            "timestamp": f.timestamp.isoformat(),
                        }
                        for f in fills
                    ],
                })

            entry_chain = {
                "snapshot": {
                    "price": snapshot.price if snapshot else None,
                    "bid": snapshot.bid if snapshot else None,
                    "ask": snapshot.ask if snapshot else None,
                    "indicators": snapshot.indicators if snapshot else None,
                    "market_context": snapshot.market_context if snapshot else None,
                    "timestamp": snapshot.timestamp.isoformat() if snapshot else None,
                } if snapshot else None,
                "signal": {
                    "strategy_name": signal.strategy_name if signal else None,
                    "direction": signal.direction.value if signal else None,
                    "strength": signal.strength if signal else None,
                    "reasoning": signal.reasoning if signal else None,
                } if signal else None,
                "decision": {
                    "action": decision.action.value,
                    "risk_evaluation": decision.risk_evaluation,
                    "reasoning": decision.decision_reasoning,
                    "stop_price": decision.stop_price,
                    "target_price": decision.target_price,
                },
                "orders": order_data,
            }

    # Get outcome
    outcome_result = await session.execute(
        select(TradeOutcome).where(TradeOutcome.position_id == trade_id)
    )
    outcome = outcome_result.scalars().first()

    return {
        "position": {
            "id": position.id,
            "symbol": position.symbol.value,
            "direction": position.direction.value,
            "quantity": position.quantity,
            "entry_price": position.entry_price,
            "exit_price": position.exit_price,
            "is_open": position.is_open,
        },
        "entry_chain": entry_chain,
        "outcome": {
            "pnl": outcome.pnl,
            "r_multiple": outcome.r_multiple,
            "hold_duration_seconds": outcome.hold_duration_seconds,
            "analysis_notes": outcome.analysis_notes,
        } if outcome else None,
    }
