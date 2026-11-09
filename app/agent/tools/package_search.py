"""查套餐：按"想做哪一块 + 面积"匹配方案，只返回区间，不返回总价。

⚠️ 两条硬约束写在这里，不靠提示词自觉：
1. 需求不全 → 直接返回 error，模型拿到错误会自己回去问客户（错误即上下文）。
2. 返回值里没有 total_price 这个字段，模型想报精确总价也拿不到数。
"""
from __future__ import annotations

from typing import Any

from ...data.packages import all_packages
from ...services import lead_service
from .base import Tool


class PackageSearchTool(Tool):
    name = "package_search"
    description = (
        "按需求场景和面积检索智能家居方案套餐，返回价格区间、包含项、不包含项、"
        "工期。只有客户的需求信息（场景+面积）齐了才能查，否则会返回信息不足的错误。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "scenario": {"type": "string", "description": "全屋智能/灯光/安防/影音/窗帘"},
            "area": {"type": "number", "description": "建筑面积，平米"},
        },
        "required": ["scenario", "area"],
    }

    def run(self, scenario: str = "", area: float = 0,
            session_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        lead = lead_service.get(session_id or "demo") or {}
        scenario = scenario or (lead.get("scenario") or "")
        area = area or (lead.get("area") or 0)

        missing = []
        if not scenario:
            missing.append("想做哪一块（全屋智能/灯光/安防/影音）")
        if not area:
            missing.append("建筑面积")
        if missing:
            return {"error": "信息不足，先问客户：" + "、".join(missing)}

        pool = [p for p in all_packages() if p["scenario"] == scenario]
        if not pool:  # 没有这个场景的套餐，退到全屋智能
            pool = [p for p in all_packages() if p["scenario"] == "全屋智能"]

        def fit(p: dict) -> tuple[int, int]:
            """面积匹配优先，其次价格档位靠中间。"""
            inside = 0 if p["area_min"] <= area <= p["area_max"] else 1
            return (inside, abs((p["area_min"] + p["area_max"]) / 2 - area))

        pool.sort(key=fit)
        best = pool[0]
        return {
            "found": True,
            "scenario": scenario,
            "area": area,
            "package": {
                "code": best["code"], "name": best["name"], "tier": best["tier"],
                "price_min": best["price_min"], "price_max": best["price_max"],
                "includes": best["includes"], "excludes": best["excludes"],
                "duration_days": best["duration_days"], "highlight": best["highlight"],
            },
            "alternatives": [{"name": p["name"], "price_min": p["price_min"],
                              "price_max": p["price_max"]} for p in pool[1:3]],
            "note": "这是区间，不是报价；最终以现场勘测为准。",
        }
