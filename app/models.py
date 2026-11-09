"""请求/响应模型。"""
from typing import Any, Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: str = "demo"


class ChatResponse(BaseModel):
    reply: str
    handoff: bool = False
    ticket_id: Optional[int] = None
    survey_id: Optional[int] = None
    trace: list[dict[str, Any]] = []
    lead: dict[str, Any] = {}
    slots_filled: int = 0
    slots_total: int = 6


class TeachRequest(BaseModel):
    """教学模式：客户问题 + 标准答案 + 这么答的原因。"""
    question: str
    answer: str
    note: str = ""
    scene: str = ""


class TicketTeachRequest(BaseModel):
    answer: str
    note: str = ""


class DirectiveUpdate(BaseModel):
    text: str


class SummaryUpdate(BaseModel):
    text: str
