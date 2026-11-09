"""查案例：按小区 / 户型 / 场景找同款完工案例。

"隔壁邻居就是这么做的"是转化率最高的一句话，所以这个工具要能给出
具体小区、具体户型、具体花了多少（区间）。
"""
from __future__ import annotations

from typing import Any

from ...data.cases import all_cases
from ...services import lead_service
from .base import Tool


class CaseSearchTool(Tool):
    name = "case_search"
    description = (
        "按小区、户型、需求场景检索已完工的真实案例，返回面积、实际花费区间、"
        "客户评价。当需要给客户信心、或客户问'有没有和我家一样的'时调用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "community": {"type": "string", "description": "小区名"},
            "layout": {"type": "string", "description": "如 三室两厅"},
            "scenario": {"type": "string", "description": "全屋智能/灯光/安防/影音"},
        },
        "required": [],
    }

    def run(self, community: str = "", layout: str = "", scenario: str = "",
            session_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        lead = lead_service.get(session_id or "demo") or {}
        community = community or (lead.get("community") or "")
        layout = layout or (lead.get("layout") or "")
        scenario = scenario or (lead.get("scenario") or "")

        cases = all_cases()
        exact = [c for c in cases if community and c["community"] == community]
        if not exact and layout:
            exact = [c for c in cases if c["layout"] == layout]
        if not exact:
            exact = cases[:2]

        # 同场景的排前面
        exact.sort(key=lambda c: (0 if c["scenario"] == scenario else 1))

        return {
            "count": len(exact),
            "exact_match": bool(community and exact[0]["community"] == community),
            "cases": [{"community": c["community"], "layout": c["layout"],
                       "area": c["area"], "scenario": c["scenario"],
                       "cost_min": c["cost_min"], "cost_max": c["cost_max"],
                       "highlight": c["highlight"], "quote": c["quote"]}
                      for c in exact[:2]],
        }
