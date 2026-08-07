from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_

from backend.database import get_session_factory
from backend.models import AbuseEvent, AppSession, AuthTransaction, SecurityAuditEvent


def main() -> None:
    now = datetime.now(timezone.utc)
    with get_session_factory()() as db:
        abuse = db.execute(
            delete(AbuseEvent).where(
                AbuseEvent.occurred_at < now - timedelta(days=30)
            )
        ).rowcount
        audit = db.execute(
            delete(SecurityAuditEvent).where(
                SecurityAuditEvent.created_at < now - timedelta(days=90)
            )
        ).rowcount
        transactions = db.execute(
            delete(AuthTransaction).where(
                or_(
                    AuthTransaction.expires_at < now,
                    AuthTransaction.consumed_at < now - timedelta(days=1),
                )
            )
        ).rowcount
        sessions = db.execute(
            delete(AppSession).where(
                AppSession.revoked_at < now - timedelta(days=30)
            )
        ).rowcount
        db.commit()
    print(
        "security_retention_complete "
        f"abuse={abuse} audit={audit} transactions={transactions} sessions={sessions}"
    )


if __name__ == "__main__":
    main()
