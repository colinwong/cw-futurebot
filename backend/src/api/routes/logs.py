from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, union_all, literal, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.db.models import Fill, NewsEvent, Order, SystemEvent

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("")
async def get_logs(
    limit: int = Query(100, le=500),
    session: AsyncSession = Depends(get_session),
):
    """Get recent activity logs from all sources: orders, fills, news, system events."""
    # Fetch recent orders
    order_result = await session.execute(
        select(Order).order_by(Order.timestamp.desc()).limit(limit)
    )
    orders = order_result.scalars().all()

    # Fetch recent fills
    fill_result = await session.execute(
        select(Fill).order_by(Fill.timestamp.desc()).limit(limit)
    )
    fills = fill_result.scalars().all()

    # Fetch recent news events
    news_result = await session.execute(
        select(NewsEvent).order_by(NewsEvent.timestamp.desc()).limit(limit)
    )
    news_items = news_result.scalars().all()

    # Fetch recent system events
    sys_result = await session.execute(
        select(SystemEvent).order_by(SystemEvent.timestamp.desc()).limit(limit)
    )
    sys_events = sys_result.scalars().all()

    # Merge into unified log entries
    entries = []

    for o in orders:
        status = o.status.value
        msg = f"{o.side.value} {o.symbol.value} {o.order_type.value} x{o.quantity}"
        if o.limit_price:
            msg += f" @ {o.limit_price:.2f}"
        if o.stop_price:
            msg += f" stop {o.stop_price:.2f}"
        msg += f" — {status}"
        entries.append({
            "timestamp": o.timestamp.isoformat(),
            "type": "order",
            "message": msg,
        })

    for f in fills:
        entries.append({
            "timestamp": f.timestamp.isoformat(),
            "type": "fill",
            "message": f"Filled @ {f.fill_price:.2f} x{f.quantity} (commission: ${f.commission:.2f})",
        })

    for n in news_items:
        impact = n.impact_rating.value if n.impact_rating else "?"
        sentiment = n.sentiment.value if n.sentiment else "?"
        entries.append({
            "timestamp": n.timestamp.isoformat(),
            "type": "news",
            "message": f"[{impact}] [{sentiment}] {n.headline}",
        })

    for s in sys_events:
        entries.append({
            "timestamp": s.timestamp.isoformat(),
            "type": "system",
            "message": f"{s.event_type.value}: {str(s.details)[:100]}",
        })

    # Sort all entries by timestamp descending
    entries.sort(key=lambda e: e["timestamp"], reverse=True)

    return {"entries": entries[:limit]}
