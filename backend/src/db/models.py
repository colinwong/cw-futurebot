import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# --- Enums ---


class SymbolEnum(str, enum.Enum):
    ES = "ES"
    NQ = "NQ"


class DirectionEnum(str, enum.Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class DecisionActionEnum(str, enum.Enum):
    EXECUTE = "EXECUTE"
    REJECT = "REJECT"
    MODIFY = "MODIFY"
    DEFER = "DEFER"


class OrderTypeEnum(str, enum.Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class OrderSideEnum(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class SentimentEnum(str, enum.Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class ImpactRatingEnum(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ProtectiveOrderStatusEnum(str, enum.Enum):
    ACTIVE = "ACTIVE"
    TRIGGERED = "TRIGGERED"
    CANCELLED = "CANCELLED"


class SystemEventTypeEnum(str, enum.Enum):
    STARTUP = "STARTUP"
    SHUTDOWN = "SHUTDOWN"
    DISCONNECT = "DISCONNECT"
    RECONNECT = "RECONNECT"
    RECONCILIATION = "RECONCILIATION"
    ERROR = "ERROR"


# --- Models ---


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    symbol: Mapped[SymbolEnum] = mapped_column(Enum(SymbolEnum))
    price: Mapped[float] = mapped_column(Float)
    bid: Mapped[float] = mapped_column(Float)
    ask: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)
    indicators: Mapped[dict] = mapped_column(JSONB, default=dict)  # EMA, RSI, VWAP, etc.
    market_context: Mapped[dict] = mapped_column(JSONB, default=dict)  # session type, time to open/close

    signals: Mapped[list["Signal"]] = relationship(back_populates="snapshot")


class NewsEvent(Base):
    __tablename__ = "news_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source: Mapped[str] = mapped_column(String(50))
    headline: Mapped[str] = mapped_column(Text)
    symbols: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Claude analysis fields
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-10
    sentiment: Mapped[SentimentEnum | None] = mapped_column(Enum(SentimentEnum), nullable=True)
    impact_rating: Mapped[ImpactRatingEnum | None] = mapped_column(
        Enum(ImpactRatingEnum), nullable=True
    )
    analysis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # full Claude response
    is_significant: Mapped[bool] = mapped_column(Boolean, default=False)


signal_news = Table(
    "signal_news",
    Base.metadata,
    Column("signal_id", Integer, ForeignKey("signals.id"), primary_key=True),
    Column("news_event_id", Integer, ForeignKey("news_events.id"), primary_key=True),
)


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("market_snapshots.id"))
    strategy_name: Mapped[str] = mapped_column(String(100))
    symbol: Mapped[SymbolEnum] = mapped_column(Enum(SymbolEnum))
    direction: Mapped[DirectionEnum] = mapped_column(Enum(DirectionEnum))
    strength: Mapped[float] = mapped_column(Float)  # 0.0 - 1.0 confidence
    reasoning: Mapped[dict] = mapped_column(JSONB, default=dict)

    snapshot: Mapped[MarketSnapshot] = relationship(back_populates="signals")
    news_events: Mapped[list[NewsEvent]] = relationship(secondary=signal_news)
    decision: Mapped["Decision | None"] = relationship(back_populates="signal")


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id"), unique=True)
    action: Mapped[DecisionActionEnum] = mapped_column(Enum(DecisionActionEnum))
    risk_evaluation: Mapped[dict] = mapped_column(JSONB, default=dict)
    decision_reasoning: Mapped[str] = mapped_column(Text)
    stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    signal: Mapped[Signal] = relationship(back_populates="decision")
    orders: Mapped[list["Order"]] = relationship(back_populates="decision")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decision_id: Mapped[int | None] = mapped_column(ForeignKey("decisions.id"), nullable=True)
    symbol: Mapped[SymbolEnum] = mapped_column(Enum(SymbolEnum))
    side: Mapped[OrderSideEnum] = mapped_column(Enum(OrderSideEnum))
    order_type: Mapped[OrderTypeEnum] = mapped_column(Enum(OrderTypeEnum))
    quantity: Mapped[int] = mapped_column(Integer)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    ib_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[OrderStatusEnum] = mapped_column(
        Enum(OrderStatusEnum), default=OrderStatusEnum.PENDING
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)

    decision: Mapped[Decision | None] = relationship(back_populates="orders")
    fills: Mapped[list["Fill"]] = relationship(back_populates="order")


class Fill(Base):
    __tablename__ = "fills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    fill_price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer)
    commission: Mapped[float] = mapped_column(Float, default=0.0)
    slippage: Mapped[float] = mapped_column(Float, default=0.0)  # vs signal price
    ib_execution_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    order: Mapped[Order] = relationship(back_populates="fills")


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[SymbolEnum] = mapped_column(Enum(SymbolEnum))
    direction: Mapped[DirectionEnum] = mapped_column(Enum(DirectionEnum))
    quantity: Mapped[int] = mapped_column(Integer)
    entry_price: Mapped[float] = mapped_column(Float)
    entry_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entry_decision_id: Mapped[int | None] = mapped_column(
        ForeignKey("decisions.id"), nullable=True
    )
    exit_decision_id: Mapped[int | None] = mapped_column(
        ForeignKey("decisions.id"), nullable=True
    )
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)

    entry_decision: Mapped[Decision | None] = relationship(foreign_keys=[entry_decision_id])
    exit_decision: Mapped[Decision | None] = relationship(foreign_keys=[exit_decision_id])
    protective_orders: Mapped[list["ProtectiveOrder"]] = relationship(back_populates="position")
    trade_outcome: Mapped["TradeOutcome | None"] = relationship(back_populates="position")


class TradeOutcome(Base):
    __tablename__ = "trade_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), unique=True)
    pnl: Mapped[float] = mapped_column(Float)
    r_multiple: Mapped[float | None] = mapped_column(Float, nullable=True)
    hold_duration_seconds: Mapped[int] = mapped_column(Integer)
    entry_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("market_snapshots.id"), nullable=True
    )
    exit_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("market_snapshots.id"), nullable=True
    )
    analysis_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    position: Mapped[Position] = relationship(back_populates="trade_outcome")
    entry_snapshot: Mapped[MarketSnapshot | None] = relationship(
        foreign_keys=[entry_snapshot_id]
    )
    exit_snapshot: Mapped[MarketSnapshot | None] = relationship(
        foreign_keys=[exit_snapshot_id]
    )


class StrategyLog(Base):
    __tablename__ = "strategy_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    strategy_name: Mapped[str] = mapped_column(String(100))
    symbol: Mapped[SymbolEnum] = mapped_column(Enum(SymbolEnum))
    state: Mapped[dict] = mapped_column(JSONB, default=dict)


class ProtectiveOrder(Base):
    __tablename__ = "protective_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"))
    stop_order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    target_order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    stop_ib_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_ib_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[ProtectiveOrderStatusEnum] = mapped_column(
        Enum(ProtectiveOrderStatusEnum), default=ProtectiveOrderStatusEnum.ACTIVE
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    position: Mapped[Position] = relationship(back_populates="protective_orders")
    stop_order: Mapped[Order | None] = relationship(foreign_keys=[stop_order_id])
    target_order: Mapped[Order | None] = relationship(foreign_keys=[target_order_id])


class SystemEvent(Base):
    __tablename__ = "system_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    event_type: Mapped[SystemEventTypeEnum] = mapped_column(Enum(SystemEventTypeEnum))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
