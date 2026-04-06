from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings as app_config
from src.db.database import get_session
from src.db.models import AppSetting, SettingsAudit

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Configurable settings with defaults and metadata
SETTING_DEFAULTS = {
    "display_timezone": {
        "default": "America/New_York",
        "type": "str",
        "label": "Display Timezone",
        "tooltip": "Timezone used to display all timestamps in the UI. Does not affect trading logic — trading always uses exchange time (ET).",
    },
    "max_position_size": {
        "default": str(app_config.max_position_size),
        "type": "int",
        "label": "Max Position Size",
        "tooltip": "Maximum number of contracts allowed per symbol (ES or NQ) at any time. New signals are rejected if this limit is reached.",
    },
    "daily_loss_limit": {
        "default": str(app_config.daily_loss_limit),
        "type": "float",
        "label": "Daily Loss Limit ($)",
        "tooltip": "Maximum realized loss in dollars per trading day (resets at ET midnight). All new trade signals are rejected once this limit is hit. Existing positions and their protective orders remain active.",
    },
    "default_stop_ticks": {
        "default": str(app_config.default_stop_ticks),
        "type": "int",
        "label": "Default Stop Loss (ticks)",
        "tooltip": "Default stop-loss distance in ticks from entry price when a strategy doesn't specify one. 1 tick = $0.25. Example: 20 ticks = $5.00 move = $25 risk per MES contract ($10 per MNQ contract).",
    },
    "default_target_ticks": {
        "default": str(app_config.default_target_ticks),
        "type": "int",
        "label": "Default Profit Target (ticks)",
        "tooltip": "Default profit target distance in ticks from entry price. Example: 40 ticks = $10.00 move = $50 profit per MES contract ($20 per MNQ contract). A 2:1 target-to-stop ratio means target should be ~2x the stop distance.",
    },
    "strategy_eval_interval": {
        "default": str(app_config.strategy_eval_interval),
        "type": "int",
        "label": "Strategy Eval Interval (seconds)",
        "tooltip": "How often the bot evaluates all active strategies for potential trade signals. Lower values (e.g., 10s) = more responsive to market changes but higher CPU/API usage. Higher values (e.g., 60s) = less resource usage but may miss fast-moving opportunities.",
    },
    "reconciliation_interval": {
        "default": str(app_config.reconciliation_interval),
        "type": "int",
        "label": "Reconciliation Interval (seconds)",
        "tooltip": "How often the bot verifies that database positions match broker positions and that protective orders (stop-loss/profit-target) are still active at IB. This is a safety net — if the bot crashes and restarts, reconciliation detects and resolves any state drift. Default 300s (5 min).",
    },
    "news_analysis_model": {
        "default": app_config.news_analysis_model,
        "type": "str",
        "label": "News Analysis Model",
        "tooltip": "Claude model used to analyze incoming news for market relevance, sentiment, and impact. claude-sonnet-4-6 is fast and cost-effective. claude-opus-4-6 is more accurate for nuanced analysis but slower and more expensive per call.",
    },
    "trading_mode": {
        "default": app_config.trading_mode,
        "type": "str",
        "label": "Trading Mode",
        "tooltip": "Controls whether the algo engine executes trades or just generates signals. 'signal_only' shows signals in the feed without placing orders — use this for observation and testing. 'live' will automatically place bracket orders at IB when signals fire. Always start with signal_only and switch to live only after you trust the strategy.",
    },
}


@router.get("")
async def get_settings(session: AsyncSession = Depends(get_session)):
    """Get all settings with current values, defaults, and metadata."""
    result = await session.execute(select(AppSetting))
    db_settings = {s.key: s.value for s in result.scalars().all()}

    settings = {}
    for key, meta in SETTING_DEFAULTS.items():
        settings[key] = {
            "value": db_settings.get(key, meta["default"]),
            "default": meta["default"],
            "type": meta["type"],
            "label": meta["label"],
            "tooltip": meta["tooltip"],
        }

    return {"settings": settings}


class UpdateSettingsRequest(BaseModel):
    settings: dict[str, str]


@router.put("")
async def update_settings(
    req: UpdateSettingsRequest,
    session: AsyncSession = Depends(get_session),
):
    """Update one or more settings. Logs changes to audit trail."""
    # Get current values
    result = await session.execute(select(AppSetting))
    current = {s.key: s for s in result.scalars().all()}

    updated = []
    for key, new_value in req.settings.items():
        if key not in SETTING_DEFAULTS:
            continue

        new_value_str = str(new_value)
        old_value = None

        if key in current:
            old_value = current[key].value
            if old_value == new_value_str:
                continue
            current[key].value = new_value_str
            current[key].updated_at = datetime.now(timezone.utc)
        else:
            old_value = SETTING_DEFAULTS[key]["default"]
            if old_value == new_value_str:
                continue
            setting = AppSetting(key=key, value=new_value_str)
            session.add(setting)

        # Audit log
        audit = SettingsAudit(
            key=key,
            old_value=old_value,
            new_value=new_value_str,
            changed_by="ui",
        )
        session.add(audit)
        updated.append(key)

    await session.commit()
    return {"updated": updated}


@router.get("/audit")
async def get_settings_audit(
    limit: int = Query(50, le=200),
    session: AsyncSession = Depends(get_session),
):
    """Get settings change history."""
    result = await session.execute(
        select(SettingsAudit).order_by(SettingsAudit.timestamp.desc()).limit(limit)
    )
    audits = result.scalars().all()

    return {
        "audits": [
            {
                "id": a.id,
                "timestamp": a.timestamp.isoformat(),
                "key": a.key,
                "label": SETTING_DEFAULTS.get(a.key, {}).get("label", a.key),
                "old_value": a.old_value,
                "new_value": a.new_value,
                "changed_by": a.changed_by,
            }
            for a in audits
        ]
    }
