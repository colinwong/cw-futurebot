from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

from src.db.models import DirectionEnum, SymbolEnum


@dataclass
class AccountInfo:
    balance: float
    unrealized_pnl: float
    realized_pnl: float
    margin_used: float
    buying_power: float


@dataclass
class BrokerPosition:
    symbol: str
    quantity: int  # positive for long, negative for short
    avg_price: float
    unrealized_pnl: float


@dataclass
class BrokerOrder:
    order_id: int
    symbol: str
    side: str  # BUY or SELL
    order_type: str
    quantity: int
    limit_price: float | None
    stop_price: float | None
    status: str
    parent_id: int | None = None


@dataclass
class BracketOrderResult:
    entry_order_id: int
    stop_order_id: int
    target_order_id: int


@dataclass
class ExecutionDetail:
    execution_id: str
    order_id: int
    symbol: str
    side: str
    quantity: int
    price: float
    commission: float
    time: str


class BaseBroker(ABC):
    """Abstract broker interface. All broker implementations must implement these methods."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the broker."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the broker."""

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if broker connection is active."""

    @abstractmethod
    async def get_account(self) -> AccountInfo:
        """Get current account information."""

    @abstractmethod
    async def get_positions(self) -> list[BrokerPosition]:
        """Get all open positions from the broker."""

    @abstractmethod
    async def get_open_orders(self) -> list[BrokerOrder]:
        """Get all working/open orders from the broker."""

    @abstractmethod
    async def get_executions(self, since: str | None = None) -> list[ExecutionDetail]:
        """Get execution history. Optionally filter by time."""

    @abstractmethod
    async def place_order(
        self,
        symbol: SymbolEnum,
        side: str,
        order_type: str,
        quantity: int,
        limit_price: float | None = None,
        stop_price: float | None = None,
    ) -> int:
        """Place a single order. Returns broker order ID."""

    @abstractmethod
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
        """Place a bracket order (entry + stop-loss + profit target as OCA group).
        Returns IDs for all three orders."""

    @abstractmethod
    async def cancel_order(self, order_id: int) -> None:
        """Cancel a specific order by broker order ID."""

    @abstractmethod
    async def modify_order(
        self,
        order_id: int,
        limit_price: float | None = None,
        stop_price: float | None = None,
        quantity: int | None = None,
    ) -> None:
        """Modify an existing order's price or quantity."""

    @abstractmethod
    def on_order_status(self, callback: Callable) -> None:
        """Register callback for order status changes."""

    @abstractmethod
    def on_execution(self, callback: Callable) -> None:
        """Register callback for trade executions/fills."""

    @abstractmethod
    def on_connection_status(self, callback: Callable) -> None:
        """Register callback for connection status changes (connect/disconnect)."""
