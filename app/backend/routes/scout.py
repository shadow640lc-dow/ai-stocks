import logging

from fastapi import APIRouter, HTTPException

from app.backend.models.scout import ScoutAlert
from app.backend.services.scout_executor import maybe_execute_scout_order
from app.backend.services.scout_service import scout_service


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/scout",
    tags=["AI Scout"],
)


@router.get("/status")
async def scout_status():
    return {
        "status": "online",
        "service": "AI Scout",
        "version": "3.1",
        "mode": "alert-only",
        "trading_enabled": False,
    }


@router.post("/webhook")
async def scout_webhook(alert: ScoutAlert):
    """
    Receive a TradingView-style alert and run AI Scout.

    Research is always performed. Real execution is opt-in and
    heavily gated:
        - SCOUT_EXECUTION_ENABLED must be "true"
        - the alert must carry the matching SCOUT_EXECUTION_SECRET
        - classification must be HIGH_INTEREST or INVESTIGATE
        - alert data must not conflict with market data
        - ALPACA_MAX_NOTIONAL caps the order size
    """

    try:
        result = await scout_service.investigate(
            ticker=alert.ticker,
            action=alert.action,
            price=alert.price,
            timeframe=alert.timeframe,
            message=alert.message,
        )

        report = result.get(
            "human_summary",
            "AI Scout did not generate a report.",
        )

        # Print the human-readable report to the server terminal.
        logger.info(
            "\n\n%s\n",
            report,
        )

        execution = maybe_execute_scout_order(alert, result)

        if execution.get("status") == "ORDER_SUBMITTED":
            logger.info(
                "SCOUT EXECUTION: %s %s %s x %s (id=%s)",
                execution.get("ticker"),
                execution.get("action"),
                execution.get("qty"),
                execution.get("side"),
                execution.get("order", {}).get("id"),
            )
        else:
            logger.info(
                "SCOUT execution refused/not attempted: %s",
                execution.get("reason"),
            )

        return {
            "scout": "AI Scout",
            "ticker": alert.ticker.upper(),
            "status": "ALERT_PROCESSED",
            "classification": result.get(
                "classification",
                "WATCH",
            ),
            "confidence": result.get(
                "confidence",
                0,
            ),
            "report": report,
            "trading_enabled": execution.get("approved", False),
            "execution": execution,
        }

    except Exception as exc:
        logger.exception(
            "AI Scout webhook failed"
        )

        raise HTTPException(
            status_code=500,
            detail={
                "error": "AI Scout analysis failed",
                "message": str(exc),
                "trading_enabled": False,
            },
        )
