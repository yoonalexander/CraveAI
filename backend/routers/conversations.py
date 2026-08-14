from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from backend.services.product_data import (
    append_message,
    clear_conversations,
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations_page,
    rename_conversation,
)
from backend.services.sessions import SessionContext, require_csrf, require_verified_session

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=60)
    first_prompt: str | None = Field(default=None, max_length=2000)


class ConversationRename(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=60)


class MessageImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=12000)
    place_ids: list[str] = Field(default_factory=list, max_length=20)


@router.get("")
async def conversations(
    limit: int = Query(default=30, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=80),
    session: SessionContext = Depends(require_verified_session),
) -> dict:
    return await list_conversations_page(session.user_id, limit, cursor)


@router.post("", status_code=status.HTTP_201_CREATED)
async def new_conversation(
    payload: ConversationCreate,
    session: SessionContext = Depends(require_csrf),
) -> dict:
    return await create_conversation(session.user_id, payload.title, payload.first_prompt)


@router.get("/{conversation_id}")
async def conversation_detail(
    conversation_id: str,
    session: SessionContext = Depends(require_verified_session),
) -> dict:
    item = await get_conversation(session.user_id, conversation_id)
    if item is None:
        raise HTTPException(status_code=404, detail={"code": "conversation_not_found"})
    return item


@router.post("/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
async def import_message(
    conversation_id: str,
    payload: MessageImport,
    session: SessionContext = Depends(require_csrf),
) -> dict:
    if not await append_message(session.user_id, conversation_id, payload.role, payload.content, payload.place_ids):
        raise HTTPException(status_code=404, detail={"code": "conversation_not_found"})
    return {"status": "saved"}


@router.patch("/{conversation_id}")
async def rename(
    conversation_id: str,
    payload: ConversationRename,
    session: SessionContext = Depends(require_csrf),
) -> dict:
    if not await rename_conversation(session.user_id, conversation_id, payload.title.strip()):
        raise HTTPException(status_code=404, detail={"code": "conversation_not_found"})
    return {"status": "renamed"}


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(
    conversation_id: str,
    session: SessionContext = Depends(require_csrf),
) -> None:
    if not await delete_conversation(session.user_id, conversation_id):
        raise HTTPException(status_code=404, detail={"code": "conversation_not_found"})


@router.delete("")
async def clear(
    session: SessionContext = Depends(require_csrf),
) -> dict:
    return {"deleted": await clear_conversations(session.user_id)}
