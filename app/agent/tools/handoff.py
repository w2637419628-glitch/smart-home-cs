"""转人工：答不上来就承认，并留下工单。

工单是本项目"自进化"的第二个入口：
答不上 → 建工单 → 店长补答案 → 待审 → 通过 → 归纳进总纲 → 下次答对。
"""
from __future__ import annotations

from typing import Any

from .base import Tool


class HandoffTool(Tool):
    name = "handoff"
    description = (
        "当问题超出你学过的范围、或需要你没有的事实（价格权限、特殊工艺、承诺类问题）时，"
        "转接人工顾问并生成工单。不要编造答案。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "客户的最后一句话，原样复制，不要改写、不要加\"客户问：\"之类的前缀",
            },
            "context": {"type": "string", "description": "转人工的原因/上下文"},
        },
        "required": ["question"],
    }

    def run(self, question: str = "", context: str = "",
            session_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        # 走 review_service，这样同一个问题不会被重复建单
        from ...services import review_service
        ticket_id = review_service.open_ticket(
            session_id or "demo", question, context or "", kind="ticket")
        return {"ticket_id": ticket_id, "status": "open",
                "message": "已为您转接人工顾问，稍后会有专人跟进。"}
