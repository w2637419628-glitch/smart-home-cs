"""约上门勘测：把高意向客户推进到"到店/到家"这一步。

这是本项目的"正向"动作（对比 handoff 是"兜底"）：
同一个工具位，一个负责推进成交，一个负责承认不会。
"""
from __future__ import annotations

from typing import Any

from ...db import cursor
from ...services import lead_service
from .base import Tool


class BookSurveyTool(Tool):
    name = "book_survey"
    description = (
        "帮客户预约免费上门勘测。需要小区、户型、面积、手机号；缺手机号会返回错误，"
        "需要先跟客户要联系方式。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "community": {"type": "string", "description": "小区名"},
            "layout": {"type": "string", "description": "户型"},
            "area": {"type": "number", "description": "面积"},
            "phone": {"type": "string", "description": "客户手机号"},
        },
        "required": [],
    }

    def run(self, community: str = "", layout: str = "", area: float = 0,
            phone: str = "", session_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        sid = session_id or "demo"
        lead = lead_service.get(sid) or {}
        phone = phone or (lead.get("phone") or "")
        if not phone:
            return {"error": "还缺手机号，先跟客户要一个联系方式才能约勘测。"}

        community = community or lead.get("community") or ""
        layout = layout or lead.get("layout") or ""
        area = area or lead.get("area") or 0
        summary = f"{community} {layout} {area:g}平".strip()

        with cursor() as cur:
            cur.execute(
                "INSERT INTO tickets (kind, session_id, question, context, status) "
                "VALUES ('survey', ?, ?, ?, 'open')",
                (sid, f"【上门勘测】{summary}",
                 f"手机号 {phone}；场景 {lead.get('scenario') or '未填'}；"
                 f"预算 {lead.get('budget') or '未填'}；装修阶段 {lead.get('stage_reno') or '未填'}"),
            )
            survey_id = cur.lastrowid

        lead_service.set_stage(sid, "survey_booked")
        return {
            "survey_id": survey_id,
            "status": "booked",
            "message": "已登记，顾问会在 2 小时内电话确认具体上门时间。",
            "summary": summary,
        }
