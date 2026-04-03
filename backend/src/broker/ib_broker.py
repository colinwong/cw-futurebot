import logging
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

    def __init__(self):
        self._ib = IB()
        self._order_status_callbacks: list[Callable] = []
        self._execution_callbacks: list[Callable] = []
        self._connection_callbacks: list[Callable] = []

    async def connect(self) -> None:
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

        logger.info("Connected to IB Gateway")

    async def disconnect(self) -> None:
        if self._ib.isConnected():
            self._ib.disconnect()
            logger.info("Disconnected from IB Gateway")

    async def is_connected(self) -> bool:
        return self._ib.isConnected()

    async def get_account(self) -> AccountInfo:
        self._ib.reqAccountSummary()
        summary = self._ib.accountSummary()

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
            if pos.contract.secType == "FUT" and pos.contract.symbol in ("ES", "NQ"):
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
        contract = make_ib_contract(symbol)
        self._ib.qualifyContracts(contract)

        side = "BUY" if direction == DirectionEnum.LONG else "SELL"
        exit_side = "SELL" if direction == DirectionEnum.LONG else "BUY"

        # Create bracket order using IB's bracket order mechanism
        bracket = self._ib.bracketOrder(
            action=side,
            quantity=quantity,
            limitPrice=entry_price or 0,
            takeProfitPrice=target_price,
            stopLossPrice=stop_price,
        )

        # If market order, change the parent order type
        parent_order = bracket[0]
        if entry_order_type == "MARKET":
            parent_order.orderType = "MKT"
            parent_order.lmtPrice = 0

        # Place all three orders
        trades = []
        for order in bracket:
            trade = self._ib.placeOrder(contract, order)
            trades.append(trade)

        result = BracketOrderResult(
            entry_order_id=trades[0].order.orderId,
            target_order_id=trades[1].order.orderId,
            stop_order_id=trades[2].order.orderId,
        )

        logger.info(
            "Placed bracket order for %s %s: entry=%d, stop=%d, target=%d (stop=%.2f, target=%.2f)",
            direction.value,
            symbol.value,
            result.entry_order_id,
            result.stop_order_id,
            result.target_order_id,
            stop_price,
            target_price,
        )
        return result

    async def cancel_order(self, order_id: int) -> None:
        trades = self._ib.trades()
        for trade in trades:
            if trade.order.orderId == order_id:
                self._ib.cancelOrder(trade.order)
                logger.info("Cancelled order %d", order_id)
                return
        logger.warning("Order %d not found for cancellation", order_id)

    async def modify_order(
        self,
        order_id: int,
        limit_price: float | None = None,
        stop_price: float | None = None,
        quantity: int | None = None,
    ) -> None:
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
