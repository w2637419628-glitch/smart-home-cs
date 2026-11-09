"""键值设置：业务铁律 / 套路总纲 / 上一版总纲 / 合规词。

总纲是"自进化"最后落地的地方——它每轮被拼进系统提示词，
所以总纲一改，AI 的下一句话就变了。
"""
from __future__ import annotations

from ..db import cursor

_KEY_DIRECTIVE = "business_directive"
_KEY_SUMMARY = "playbook_summary"
_KEY_SUMMARY_PREV = "playbook_summary_prev"

DEFAULT_DIRECTIVE = (
    "【语气】简洁、口语化，一次回复一般不超过 3 句；先回应客户最关心的点，别长篇大论。\n"
    "【铁律】\n"
    "1. 绝不报精确总价，只给区间，并说明「以现场勘测为准」。\n"
    "2. 客户问价时，先问清六件事：想做哪一块、面积、户型、装修阶段、预算、小区。\n"
    "3. 需求没问全，绝不推荐具体套餐。\n"
    "4. 不承诺具体工期，不承诺「绝对稳定 / 零故障」，不贬低同行。\n"
    "5. 客户表达明确意向时，主动推进「免费上门勘测」。\n"
    "6. 【常见技术可直接承诺】只要客户问的是市面上常见、不冷门的工艺"
    "（例如弧形柜、隐形门、悬浮楼梯、卡座、封阳台等），可以直接回答「能做」，"
    "并补一句「具体以现场勘测和出图为准」。"
    "只有明显冷门、需要外协、或涉及拆改承重结构的工艺，才转人工确认。"
)


def _get(key: str, default: str = "") -> str:
    with cursor() as cur:
        cur.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
    return row["value"] if row else default


def _set(key: str, value: str) -> None:
    with cursor() as cur:
        cur.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_directive() -> str:
    return _get(_KEY_DIRECTIVE, DEFAULT_DIRECTIVE)


def set_directive(text: str) -> dict:
    _set(_KEY_DIRECTIVE, text)
    return {"ok": True}


def get_summary() -> str:
    return _get(_KEY_SUMMARY, "")


def get_summary_prev() -> str:
    return _get(_KEY_SUMMARY_PREV, "")


def set_summary(text: str, keep_prev: bool = True) -> dict:
    """保存新总纲；把旧的总纲留一份，用于展示「这次多了哪几条」。"""
    old = get_summary()
    if keep_prev and old.strip() and old != text:
        _set(_KEY_SUMMARY_PREV, old)
    _set(_KEY_SUMMARY, text)
    return {"ok": True}
