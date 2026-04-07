import asyncio
import concurrent.futures
import logging
import uuid
from typing import Callable

from ib_insync import IB, LimitOrder, MarketOrder, StopOrder, Trade

from src.broker.base import (
    AccountInfo,
    BaseBroker,
    BracketOrderResult,
    BrokerOrder,
    BrokerPosition,
    ExecutionDetail,
)
from src.config import settings
from src.contracts import make_ib_contract
from src.db.models import DirectionEnum, SymbolEnum

logger = logging.getLogger(__name__)


class IBBroker(BaseBroker):
    """Interactive Brokers implementation using ib_insync."""

    def __init__(self, ib_instance: IB | None = None, executor: concurrent.futures.ThreadPoolExecutor | None = None):
        self._ib = ib_instance or IB()
        self._executor = executor
        self._order_status_callbacks: list[Callable] = []
        self._execution_callbacks: list[Callable] = []
        self._connection_callbacks: list[Callable] = []

    async def _run(self, fn, *args, timeout: float = 30.0, **kwargs):
        """Run a sync ib_insync call in the IB thread pool with timeout."""
        if self._executor:
            def _call():
                loop = asyncio.get_event_loop()
                if loop is None or loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                return fn(*args, **kwargs)
            return await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(self._executor, _call),
                timeout=timeout,
            )
        return fn(*args, **kwargs)

    async def connect(self) -> None:
        if self._ib.isConnected():
            logger.info("IBBroker using existing IB connection")
        else:
            logger.info(
                "Connecting to IB Gateway at %s:%d (client_id=%d)",
                settings.ib_host,
                settings.ib_port,
                settings.ib_client_id,
            )
            self._ib.connect(
                host=settings.ib_host,
                port=settings.ib_port,
                clientId=settings.ib_client_id,
                readonly=False,
            )

        # Register event handlers
        self._ib.orderStatusEvent += self._handle_order_status
        self._ib.execDetailsEvent += self._handle_execution
        self._ib.connectedEvent += lambda: self._handle_connection(True)
        self._ib.disconnectedEvent += lambda: self._handle_connection(False)

        logger.info("IBBroker ready")

    async def disconnect(self) -> None:
        if self._ib.isConnected():
            self._ib.disconnect()
            logger.info("Disconnected from IB Gateway")

    async def is_connected(self) -> bool:
        return self._ib.isConnected()

    async def get_account(self) -> AccountInfo:
        summary = await self._run(self._ib.accountSummary)
        if not summary:
            await self._run(self._ib.reqAccountSummary)
            summary = await self._run(self._ib.accountSummary)

        values = {}
        for item in summary:
            if item.account == settings.ib_account or not settings.ib_account:
                values[item.tag] = item.value

        return AccountInfo(
            balance=float(values.get("NetLiquidation", 0)),
            unrealized_pnl=float(values.get("UnrealizedPnL", 0)),
            realized_pnl=float(values.get("RealizedPnL", 0)),
            margin_used=float(values.get("InitMarginReq", 0)),
            buying_power=float(values.get("BuyingPower", 0)),
        )

    async def get_positions(self) -> list[BrokerPosition]:
        positions = self._ib.positions()
        result = []
        for pos in positions:
            if pos.contract.secType == "FUT" and pos.contract.symbol in ("ES", "NQ", "MES", "MNQ"):
                result.append(
                    BrokerPosition(
                        symbol=pos.contract.symbol,
                        quantity=int(pos.position),
                        avg_price=pos.avgCost,
                        unrealized_pnl=pos.unrealizedPNL or 0.0,
                    )
                )
        return result

    async def get_open_orders(self) -> list[BrokerOrder]:
        orders = self._ib.openOrders()
        result = []
        for order in orders:
            trade = self._ib.trades()
            matching = [t for t in trade if t.order.orderId == order.orderId]
            status = matching[0].orderStatus.status if matching else "Unknown"
            result.append(
                BrokerOrder(
                    order_id=order.orderId,
                    symbol=order.contract.symbol if hasattr(order, "contract") else "",
                    side=order.action,
                    order_type=order.orderType,
                    quantity=int(order.totalQuantity),
                    limit_price=order.lmtPrice if order.lmtPrice != 0 else None,
                    stop_price=order.auxPrice if order.auxPrice != 0 else None,
                    status=status,
                    parent_id=order.parentId if order.parentId != 0 else None,
                )
            )
        return result

    async def get_executions(self, since: str | None = None) -> list[ExecutionDetail]:
        fills = self._ib.fills()
        result = []
        for fill in fills:
            result.append(
                ExecutionDetail(
                    execution_id=fill.execution.execId,
                    order_id=fill.execution.orderId,
                    symbol=fill.contract.symbol,
                    side=fill.execution.side,
                    quantity=int(fill.execution.shares),
                    price=fill.execution.price,
                    commission=fill.commissionReport.commission if fill.commissionReport else 0.0,
                    time=str(fill.execution.time),
                )
            )
        return result

    async def place_order(
        self,
        symbol: SymbolEnum,
        side: str,
        order_type: str,
        quantity: int,
        limit_price: float | None = None,
        stop_price: float | None = None,
    ) -> int:
        def _place():
            contract = make_ib_contract(symbol)
            self._ib.qualifyContracts(contract)

            if order_type == "MARKET":
                order = MarketOrder(side, quantity)
            elif order_type == "LIMIT":
                order = LimitOrder(side, quantity, limit_price)
            elif order_type == "STOP":
                order = StopOrder(side, quantity, stop_price)
            else:
                raise ValueError(f"Unsupported order type: {order_type}")

            trade = self._ib.placeOrder(contract, order)
            logger.info("Placed %s %s %d %s @ %s", side, symbol.value, quantity, order_type, limit_price or stop_price or "MKT")
            return trade.order.orderId

        return await self._run(_place)

    async def place_bracket_order(
        self,
        symbol: SymbolEnum,
        direction: DirectionEnum,
        quantity: int,
        entry_order_type: str,
        entry_price: float | None,
        stop_price: float,
        target_price: float,
    ) -> BracketOrderResult:
        """Place entry, wait for confirmed fill, then place OCA stop/target.
        OCA orders survive client disconnects (unlike parent-child brackets)."""

        def _place():
            contract = make_ib_contract(symbol)
            self._ib.qualifyContracts(contract)

            entry_side = "BUY" if direction == DirectionEnum.LONG else "SELL"
            exit_side = "SELL" if direction == DirectionEnum.LONG else "BUY"

            # 1. Place entry order
            if entry_order_type == "MARKET":
                entry_order = MarketOrder(entry_side, quantity)
            else:
                entry_order = LimitOrder(entry_side, quantity, entry_price)
            entry_trade = self._ib.placeOrder(contract, entry_order)

            # 2. Wait for CONFIRMED fill (up to 30s — market orders fill instantly for liquid futures)
            for _ in range(300):
                self._ib.sleep(0.1)
                if entry_trade.orderStatus.status == "Filled":
                    break

            if entry_trade.orderStatus.status != "Filled":
                # Entry didn't fill — cancel and abort
                self._ib.cancelOrder(entry_trade.order)
                self._ib.sleep(1)
                raise RuntimeError(
                    f"Entry order {entry_trade.order.orderId} did not fill within 30s — cancelled"
                )

            # 3. Entry confirmed filled — place OCA protective orders
            oca_group = f"fb_{symbol.value}_{uuid.uuid4().hex[:12]}"

            target_order = LimitOrder(exit_side, quantity, target_price)
            target_order.ocaGroup = oca_group
            target_order.ocaType = 1  # Cancel remaining on fill

            stop_order = StopOrder(exit_side, quantity, stop_price)
            stop_order.ocaGroup = oca_group
            stop_order.ocaType = 1

            target_trade = self._ib.placeOrder(contract, target_order)
            stop_trade = self._ib.placeOrder(contract, stop_order)

            return BracketOrderResult(
                entry_order_id=entry_trade.order.orderId,
                target_order_id=target_trade.order.orderId,
                stop_order_id=stop_trade.order.orderId,
            )

        result = await self._run(_place)

        logger.info(
            "Placed OCA bracket for %s %s: entry=%d, stop=%d, target=%d (stop=%.2f, target=%.2f)",
            direction.value,
            symbol.value,
            result.entry_order_id,
            result.stop_order_id,
            result.target_order_id,
            stop_price,
            target_price,
        )
        return result

    async def place_oca_protective_orders(
        self,
        symbol: SymbolEnum,
        direction: DirectionEnum,
        quantity: int,
        stop_price: float,
        target_price: float,
    ) -> tuple[int, int]:
        """Place standalone OCA stop+target for an existing position (used by reconciliation)."""

        def _place():
            contract = make_ib_contract(symbol)
            self._ib.qualifyContracts(contract)

            exit_side = "SELL" if direction == DirectionEnum.LONG else "BUY"
            oca_group = f"fb_{symbol.value}_{uuid.uuid4().hex[:12]}"

            target_order = LimitOrder(exit_side, quantity, target_price)
            target_order.ocaGroup = oca_group
            target_order.ocaType = 1

            stop_order = StopOrder(exit_side, quantity, stop_price)
            stop_order.ocaGroup = oca_group
            stop_order.ocaType = 1

            target_trade = self._ib.placeOrder(contract, target_order)
            stop_trade = self._ib.placeOrder(contract, stop_order)

            return target_trade.order.orderId, stop_trade.order.orderId

        target_id, stop_id = await self._run(_place)
        logger.info(
            "Placed OCA protective orders for %s %s x%d: stop=%d (%.2f), target=%d (%.2f)",
            direction.value, symbol.value, quantity, stop_id, stop_price, target_id, target_price,
        )
        return target_id, stop_id

    async def cancel_order(self, order_id: int) -> None:
        def _cancel():
            trades = self._ib.trades()
            for trade in trades:
                if trade.order.orderId == order_id:
                    self._ib.cancelOrder(trade.order)
                    logger.info("Cancelled order %d", order_id)
                    return
            logger.warning("Order %d not found for cancellation", order_id)

        await self._run(_cancel)

    async def modify_order(
        self,
        order_id: int,
        limit_price: float | None = None,
        stop_price: float | None = None,
        quantity: int | None = None,
    ) -> None:
        def _modify():
            trades = self._ib.trades()
            for trade in trades:
                if trade.order.orderId == order_id:
                    order = trade.order
                    if limit_price is not None:
                        order.lmtPrice = limit_price
                    if stop_price is not None:
                        order.auxPrice = stop_price
                    if quantity is not None:
                        order.totalQuantity = quantity
                    self._ib.placeOrder(trade.contract, order)
                    logger.info("Modified order %d", order_id)
                    return
            logger.warning("Order %d not found for modification", order_id)

        await self._run(_modify)

    def on_order_status(self, callback: Callable) -> None:
        self._order_status_callbacks.append(callback)

    def on_execution(self, callback: Callable) -> None:
        self._execution_callbacks.append(callback)

    def on_connection_status(self, callback: Callable) -> None:
        self._connection_callbacks.append(callback)

    def _handle_order_status(self, trade: Trade) -> None:
        for cb in self._order_status_callbacks:
            try:
                cb(trade)
            except Exception:
                logger.exception("Error in order status callback")

    def _handle_execution(self, trade: Trade, fill) -> None:
        for cb in self._execution_callbacks:
            try:
                cb(trade, fill)
            except Exception:
                logger.exception("Error in execution callback")

    def _handle_connection(self, connected: bool) -> None:
        status = "connected" if connected else "disconnected"
        logger.info("IB connection status: %s", status)
        for cb in self._connection_callbacks:
            try:
                cb(connected)
            except Exception:
                logger.exception("Error in connection status callback")
