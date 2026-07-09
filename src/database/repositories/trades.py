from sqlalchemy.orm import Session

from src.database.models import TradeDecision


def save_trade_decision(
    db: Session,
    ticker: str,
    model_name: str,
    action: str,
    quantity: int,
    confidence: float,
    reasoning: str,
):
    """
    Save an AI trading decision.
    """

    trade = TradeDecision(
        ticker=ticker,
        model_name=model_name,
        action=action,
        quantity=quantity,
        confidence=confidence,
        reasoning=reasoning,
    )

    db.add(trade)
    db.commit()
    db.refresh(trade)

    return trade


def get_trade_history(
    db: Session,
    ticker: str | None = None,
):
    """
    Retrieve previous AI decisions.
    """

    query = db.query(TradeDecision)

    if ticker:
        query = query.filter(
            TradeDecision.ticker == ticker
        )

    return query.order_by(
        TradeDecision.created_at.desc()
    ).all()
