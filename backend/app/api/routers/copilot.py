"""AI Copilot endpoints: ask, conversations, and suggested questions."""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import desc, select

from app.api.deps import PrincipalDep, SessionDep, audit, require_scope
from app.api.schemas import CopilotAnswerOut, CopilotAskRequest
from app.copilot.agent import SUGGESTED_QUESTIONS, ask
from app.core.errors import NotFoundError
from app.db.models import CopilotConversation, CopilotMessage

router = APIRouter(prefix="/copilot", tags=["copilot"])


@router.get("/suggested-questions", summary="Example questions the copilot can answer")
def suggested() -> list[str]:
    return SUGGESTED_QUESTIONS


@router.get("/status", summary="Copilot backend availability")
def status() -> dict:
    """Report whether a generative LLM is configured.

    The copilot always answers from the platform's own records (retrieval-first),
    so it is never "broken"; this tells the UI whether answers are LLM-narrated
    or produced by the deterministic engine, so it can label them honestly.
    """
    from app.copilot.llm import get_llm

    llm = get_llm()
    return {
        "available": True,
        "llm_configured": llm.available,
        "provider": llm.provider,
        "model": llm.model,
    }


@router.post(
    "/ask",
    response_model=CopilotAnswerOut,
    summary="Ask the copilot a question",
    dependencies=[__import__("fastapi").Depends(require_scope("use:copilot"))],
)
def ask_copilot(
    payload: CopilotAskRequest,
    session: SessionDep,
    principal: PrincipalDep,
    request: Request,
) -> CopilotAnswerOut:
    """Answer a regulatory question from the platform's own records."""
    conversation_context = None
    conversation = None
    if payload.conversation_id:
        conversation = session.get(CopilotConversation, payload.conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found")
        recent = list(
            session.scalars(
                select(CopilotMessage)
                .where(CopilotMessage.conversation_id == conversation.id)
                .order_by(desc(CopilotMessage.created_at))
                .limit(6)
            )
        )
        if recent:
            conversation_context = "\n".join(
                f"{m.role}: {m.content[:400]}" for m in reversed(recent)
            )

    answer = ask(session, payload.question, use_llm=payload.use_llm, conversation_context=conversation_context)

    # Persist the turn for conversation history.
    if conversation is None:
        conversation = CopilotConversation(
            user_id=principal.user_id,
            title=payload.question[:120],
        )
        session.add(conversation)
        session.flush()
    session.add(
        CopilotMessage(
            conversation_id=conversation.id,
            role="user",
            content=payload.question,
        )
    )
    session.add(
        CopilotMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=answer.answer,
            citations=answer.citations,
            tool_calls=[t.to_dict() for t in answer.tool_calls],
            model=answer.model,
            latency_ms=answer.latency_ms,
        )
    )
    audit(
        session,
        actor=principal.username,
        action="copilot_ask",
        resource_type="copilot",
        resource_id=conversation.id,
        detail={"intent": answer.intent, "question": payload.question[:200]},
        request=request,
    )
    session.commit()

    out = CopilotAnswerOut.model_validate(answer.to_dict())
    out.data = {**out.data, "conversation_id": conversation.id}
    return out


@router.get("/conversations", summary="List the current user's copilot conversations")
def list_conversations(session: SessionDep, principal: PrincipalDep) -> list[dict]:
    rows = session.scalars(
        select(CopilotConversation)
        .where(CopilotConversation.user_id == principal.user_id)
        .order_by(desc(CopilotConversation.created_at))
        .limit(50)
    )
    return [
        {
            "id": c.id,
            "title": c.title,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in rows
    ]


@router.get("/conversations/{conversation_id}", summary="Get a conversation with its messages")
def get_conversation(conversation_id: str, session: SessionDep, principal: PrincipalDep) -> dict:
    conversation = session.get(CopilotConversation, conversation_id)
    if conversation is None:
        raise NotFoundError("Conversation not found")
    messages = session.scalars(
        select(CopilotMessage)
        .where(CopilotMessage.conversation_id == conversation.id)
        .order_by(CopilotMessage.created_at)
    )
    return {
        "id": conversation.id,
        "title": conversation.title,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "citations": m.citations,
                "tool_calls": m.tool_calls,
                "model": m.model,
                "latency_ms": m.latency_ms,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }
