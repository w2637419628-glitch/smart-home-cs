"""客户档案：6 个需求槽位 + 客户阶段。

这是"挖需求"落地的地方。模型每调一次 save_requirements，
这里就多记一点；前端读它渲染"需求进度条"。
"""
from __future__ import annotations

from typing import Any

from .. import config
from ..db import cursor

_SLOT_COLUMNS = {"scenario", "area", "layout", "stage_reno", "budget", "community", "phone"}


def get(session_id: str) -> dict[str, Any] | None:
    with cursor() as cur:
        cur.execute("SELECT * FROM leads WHERE session_id=?", (session_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def get_or_create(session_id: str) -> dict[str, Any]:
    lead = get(session_id)
    if lead:
        return lead
    with cursor() as cur:
        cur.execute("INSERT OR IGNORE INTO leads (session_id) VALUES (?)", (session_id,))
        cur.execute("SELECT * FROM leads WHERE session_id=?", (session_id,))
        row = cur.fetchone()
    return dict(row)


def upsert_slots(session_id: str, slots: dict[str, Any]) -> dict[str, Any]:
    """把模型提取到的槽位写进档案（只写非空值与合法字段）。"""
    lead = get_or_create(session_id)
    updates = {k: v for k, v in (slots or {}).items()
               if k in _SLOT_COLUMNS and v not in (None, "", 0)}
    if updates:
        sets = ", ".join(f"{k}=?" for k in updates)
        vals = list(updates.values())
        with cursor() as cur:
            cur.execute(
                f"UPDATE leads SET {sets}, stage=?, updated_at=datetime('now','localtime') "
                "WHERE session_id=?",
                vals + [_next_stage({**lead, **updates}), session_id],
            )
    return get_or_create(session_id)


def set_stage(session_id: str, stage: str) -> dict[str, Any]:
    with cursor() as cur:
        cur.execute("UPDATE leads SET stage=?, updated_at=datetime('now','localtime') "
                    "WHERE session_id=?", (stage, session_id))
    return get_or_create(session_id)


def reset(session_id: str) -> None:
    """清空这个会话的客户档案（重置对话时必须一起清，否则需求进度条会残留）。"""
    with cursor() as cur:
        cur.execute("DELETE FROM leads WHERE session_id=?", (session_id,))


def missing_slots(lead: dict[str, Any]) -> list[str]:
    return [k for k in config.SLOT_KEYS if not lead.get(k)]


def filled_count(lead: dict[str, Any] | None) -> int:
    if not lead:
        return 0
    return sum(1 for k in config.SLOT_KEYS if lead.get(k))


def _next_stage(lead: dict[str, Any]) -> str:
    """阶段自动推进：信息齐了就 qualified，剩下的等 book_survey 改。"""
    if lead.get("stage") == "survey_booked":
        return "survey_booked"
    return "qualified" if not missing_slots(lead) else "inquiry"
