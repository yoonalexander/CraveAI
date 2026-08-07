from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.database import get_session_factory
from backend.models import AuthTransaction
from backend.services.security import decrypt_secret, encrypt_secret, random_token, sha256


@dataclass(frozen=True)
class TransactionContext:
    id: str
    kind: str
    state_hash: str | None
    nonce_hash: str | None
    code_verifier: str | None
    access_token: str | None
    user_id: str | None
    next_path: str


async def create_transaction(
    *,
    kind: str,
    state: str | None = None,
    nonce: str | None = None,
    code_verifier: str | None = None,
    access_token: str | None = None,
    user_id: str | None = None,
    next_path: str = "/",
    ttl_minutes: int = 10,
) -> str:
    raw = random_token()
    now = datetime.now(timezone.utc)
    row = AuthTransaction(
        id=str(uuid.uuid4()),
        transaction_hash=sha256(raw),
        kind=kind,
        state_hash=sha256(state) if state else None,
        nonce_hash=sha256(nonce) if nonce else None,
        encrypted_code_verifier=encrypt_secret(code_verifier) if code_verifier else None,
        encrypted_access_token=encrypt_secret(access_token) if access_token else None,
        user_id=user_id,
        next_path=next_path,
        created_at=now,
        expires_at=now + timedelta(minutes=ttl_minutes),
        consumed_at=None,
    )

    def _insert() -> None:
        with get_session_factory()() as db:
            db.add(row)
            db.commit()

    await asyncio.to_thread(_insert)
    return raw


async def consume_transaction(raw: str, expected_kinds: set[str]) -> TransactionContext | None:
    now = datetime.now(timezone.utc)

    def _consume() -> TransactionContext | None:
        with get_session_factory()() as db:
            row = db.scalar(
                select(AuthTransaction)
                .where(AuthTransaction.transaction_hash == sha256(raw))
                .with_for_update()
            )
            if (
                row is None
                or row.kind not in expected_kinds
                or row.consumed_at is not None
                or _utc(row.expires_at) <= now
            ):
                return None
            row.consumed_at = now
            db.commit()
            return TransactionContext(
                id=row.id,
                kind=row.kind,
                state_hash=row.state_hash,
                nonce_hash=row.nonce_hash,
                code_verifier=(
                    decrypt_secret(row.encrypted_code_verifier)
                    if row.encrypted_code_verifier
                    else None
                ),
                access_token=(
                    decrypt_secret(row.encrypted_access_token)
                    if row.encrypted_access_token
                    else None
                ),
                user_id=row.user_id,
                next_path=row.next_path,
            )

    return await asyncio.to_thread(_consume)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
