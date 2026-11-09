"""记录需求：把客户这句话里的信息写进档案，并返回"还缺什么"。

为什么把它做成工具（而不是写死在代码里）？
—— 这样"挖需求"是模型自己的动作：它会一句一句地调、一句一句地补，
    前端轨迹里能看见「它在收集信息」，而不是一个 if-else 状态机。
"""
from __future__ import annotations

from typing import Any

from ... import config
from ...services import lead_service
from .base import Tool


class SaveRequirementsTool(Tool):
    name = "save_requirements"
    description = (
        "从客户的话里提取装修需求并写入客户档案。只要客户提到了面积、户型、小区、"
        "预算、装修阶段、想做哪一块，就调用它记录下来；没提到就传空。"
        "调用后返回还缺哪些信息、下一句该问什么。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "slots": {
                "type": "object",
                "description": "本次新提取到的信息，只填客户明确提到的字段",
                "properties": {
                    "scenario": {"type": "string", "description": "全屋智能/灯光/安防/影音/窗帘"},
                    "area": {"type": "number", "description": "建筑面积，单位平米"},
                    "layout": {"type": "string", "description": "如 三室两厅"},
                    "stage_reno": {"type": "string", "description": "毛坯/硬装中/已入住"},
                    "budget": {"type": "string", "description": "如 3万"},
                    "community": {"type": "string", "description": "小区名"},
                    "phone": {"type": "string", "description": "手机号"},
                },
            }
        },
        "required": ["slots"],
    }

    def run(self, slots: dict[str, Any] | None = None,
            session_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        lead = lead_service.upsert_slots(session_id or "demo", slots or {})
        missing = [k for k in config.SLOT_KEYS if not lead.get(k)]
        labels = {k: label for k, label, _ in config.REQUIRED_SLOTS}
        return {
            "slots": {k: lead.get(k) for k in config.SLOT_KEYS if lead.get(k)},
            "missing": missing,
            "next_question": labels.get(missing[0], "") if missing else "",
            "complete": not missing,
        }
