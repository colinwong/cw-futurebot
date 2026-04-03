import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.broker.base import BaseBroker
from src.db.models import (
    Position,
    ProtectiveOrder,
    ProtectiveOrderStatusEnum,
    SystemEvent,
    SystemEventTypeEnum,
)

logger = logging.getLogger(__name__)


@dataclass
class ReconciliationResult:
    positions_matched: int = 0
    positions_closed_by_broker: list[dict] = field(default_factory=list)
    orphaned_broker_positions: list[dict] = field(default_factory=list)
    missing_protective_orders: list[dict] = field(default_factory=list)
    quantity_mismatches: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def has_discrepancies(self) -> bool:
        return bool(
            self.positions_closed_by_broker
            or self.orphaned_broker_positions
            or self.missing_protective_orders
            or self.quantity_mismatches
            or self.errors
        )

    def to_dict(self) -> dict:
        return {
            "positions_matched": self.positions_matched,
            "positions_closed_by_broker": self.positions_closed_by_broker,
            "orphaned_broker_positions": self.orphaned_broker_positions,
            "missing_protective_orders": self.missing_protective_orders,
            "quantity_mismatches": self.quantity_mismatches,
            "errors": self.errors,
        }


class Reconciler:
    """Compares DB state vs broker state and handles discrepancies.

    Run at startup and periodically during operation.
    """

    def __init__(self, broker: BaseBroker):
        self._broker = broker

    async def reconcile(self, session: AsyncSession) -> ReconciliationResult:
        result = ReconciliationResult()

        try:
            db_result = await session.execute(
                select(Position).where(Position.is_open.is_(True))
            )
            db_positions = {
                pos.symbol.value: pos for pos in db_result.scalars().all()
            }

            broker_positions = await self._broker.get_positions()
            broker_pos_map = {pos.symbol: pos for pos in broker_positions}

            for symbol, db_pos in db_positions.items():
                broker_pos = broker_pos_map.pop(symbol, None)

                if broker_pos is None:
                    result.positions_closed_by_broker.append({
                        "symbol": symbol,
                        "db_quantity": db_pos.quantity,
                        "direction": db_pos.direction.value,
                    })
                    db_pos.is_open = False
                    db_pos.exit_timestamp = datetime.now(timezone.utc)
                    logger.warning(
                        "Position %s closed by broker while bot was down", symbol
                    )

                elif abs(broker_pos.quantity) != db_pos.quantity:
                    result.quantity_mismatches.append({
                        "symbol": symbol,
                        "db_quantity": db_pos.quantity,
                        "broker_quantity": broker_pos.quantity,
                    })
                    logger.warning(
                        "Quantity mismatch for %s: DB=%d, broker=%d",
                        symbol, db_pos.quantity, broker_pos.quantity,
                    )
                else:
                    result.positions_matched += 1

            for symbol, broker_pos in broker_pos_map.items():
                if broker_pos.quantity != 0:
                    result.orphaned_broker_positions.append({
                        "symbol": symbol,
                        "quantity": broker_pos.quantity,
                        "avg_price": broker_pos.avg_price,
                    })
                    logger.warning(
                        "Orphaned broker position: %s qty=%d (not in DB)",
                        symbol, broker_pos.quantity,
                    )

            await self._verify_protective_orders(db_positions, result, session)

        except Exception as e:
            result.errors.append(str(e))
            logger.exception("Error during reconciliation")

        event = SystemEvent(
            event_type=SystemEventTypeEnum.RECONCILIATION,
            details=result.to_dict(),
        )
        session.add(event)
        await session.commit()

        if result.has_discrepancies:
            logger.warning("Reconciliation found discrepancies: %s", result.to_dict())
        else:
            logger.info(
                "Reconciliation OK: %d positions matched", result.positions_matched
            )

        return result

    async def _verify_protective_orders(
        self,
        db_positions: dict,
        result: ReconciliationResult,
        session: AsyncSession,
    ) -> None:
        broker_orders = await self._broker.get_open_orders()
        broker_order_ids = {o.order_id for o in broker_orders}

        for symbol, pos in db_positions.items():
            if not pos.is_open:
                continue

            prot_result = await session.execute(
                select(ProtectiveOrder).where(
                    ProtectiveOrder.position_id == pos.id,
                    ProtectiveOrder.status == ProtectiveOrderStatusEnum.ACTIVE,
                )
            )
            protective = prot_result.scalars().first()

            if not protective:
                result.missing_protective_orders.append({
                    "symbol": symbol,
                    "position_id": pos.id,
                    "reason": "no protective order record in DB",
                })
                continue

            stop_exists = protective.stop_ib_order_id in broker_order_ids
            target_exists = protective.target_ib_order_id in broker_order_ids

            if not stop_exists or not target_exists:
                missing = []
                if not stop_exists:
                    missing.append("stop")
                if not target_exists:
                    missing.append("target")
                result.missing_protective_orders.append({
                    "symbol": symbol,
                    "position_id": pos.id,
                    "missing_orders": missing,
                    "reason": f"protective orders missing at broker: {', '.join(missing)}",
                })
                logger.warning(
                    "Missing protective orders for %s position: %s", symbol, missing
                )
            else:
                protective.verified_at = datetime.now(timezone.utc)
