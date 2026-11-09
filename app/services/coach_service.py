"""教练服务：把样本归纳成「套路总纲」，并拼装最终生效的系统提示词。

这里是自进化的最后一公里：
    审核通过 → refresh_summary() → 总纲变了 → 下一轮提示词里就带着它 → 行为变了

四个环节：
  沉淀（样本入库）→ 归纳（LLM 写总纲）→ 注入（拼进 system prompt）→ 可回退（人工改写优先）
"""
from __future__ import annotations

import re
from typing import Any

from .. import config
from ..llm.factory import build_provider
from . import playbook_service, settings_service

# ---------------------------------------------------------------- 提示词第 1 层

BASE_PROMPT = """你是一名智能家居顾问，在一家做全屋智能的门店接待客户咨询。

可用工具：
- recall_playbook：取回店长教过的示范话术（客户问题 + 标准答案 + 这么答的原因）。回答任何问题前先调用。
- save_requirements：把客户提到的装修需求（场景/面积/户型/装修阶段/预算/小区）记进档案，并告诉你还缺什么。
- package_search：查方案套餐的价格区间、包含项、工期。需求没问全时它会返回错误。
- case_search：查同小区、同户型的真实完工案例。
- book_survey：帮客户约免费上门勘测（需要手机号）。
- handoff：问题超出你学过的范围时，转人工并建工单。绝不编造答案。

工作流程（务必遵守）：
1. 回答任何咨询前，先调用 recall_playbook。
   · 如果它返回 covered=true：这就是店长教过的类似问题，照它的话术与策略作答。
   · 如果它返回 covered=false：说明店长没教过这个具体问题，按下面顺序判断：
     a) 先看【业务铁律】里有没有对这一类问题授权（例如「常见技术可以直接说能做」）。
        有授权，就按铁律作答，并在结尾补一句「具体以现场勘测和出图为准」。
     b) 没有授权，或属于冷门工艺、需要外协、涉及结构安全（承重墙/燃气/消防）→
        必须调用 handoff 转人工，不许凭常识猜。
   铁律的优先级高于本条的一般描述，两者冲突时以铁律为准。
2. 客户一开口，先把他说到的信息用 save_requirements 记下来；没提到的字段不要瞎填。
3. 只要 save_requirements 返回 missing 非空，就要继续追问，一次只问一两项，语气自然。
4. 六个需求（场景/面积/户型/装修阶段/预算/小区）齐了之后，才允许调用 package_search。
5. 给方案时先给区间，再补一条同小区案例，最后推进「免费上门勘测」。
6. 客户问价格但信息不全时，不要报任何数字，先说明"要看完方案才能算"，然后继续追问。
7. 需要转人工的情形：冷门或需外协的工艺、涉及结构安全、需要你没有的权限（改价、承诺具体工期）。
   注意：只要你在回复里说了「让顾问跟您确认 / 转人工」，就必须真的调用 handoff 生成工单；
   光在嘴上说转接、不建单，客户会没人跟进，这是流程错误。
8. 用中文口语回答，不要暴露工具名和内部流程，不要长篇大论。
"""

# ---------------------------------------------------------------- 归纳总纲

_INDUCE_SYSTEM = (
    "你是智能家居门店的销售培训师。下面是店长教过的一批示范"
    "（客户问题 + 标准答案 + 这么答的原因）。"
    "请从中提炼出「应答套路总纲」：用条目化的通用原则写清楚"
    "（面对哪类问题该怎么应对、先做什么后做什么、什么时候先问需求、"
    "什么话绝对不能说）。要求：每一条具体经验都必须被某条原则覆盖，不能漏；"
    "只输出总纲本身，不要复述原始样本，条目控制在 12 条以内。"
)

_MERGE_SYSTEM = (
    "你是智能家居门店的销售培训师。店长已经有一份【现有套路总纲】，"
    "其中的规则和措辞倾向必须原样保留。现在给你一批新教的样本，"
    "请把样本里体现出、但现有总纲还没覆盖的新套路补充进去；"
    "若新样本与现有总纲冲突，一律以现有总纲为准。"
    "硬性要求：新增样本里每一条具体经验，都必须在更新后的总纲里有对应条目"
    "（可以合并措辞，但绝不能丢），这样店长才能看出“我教的这条被写进去了”。"
    "输出更新后的完整总纲，条目化、简洁，不要删除店长已有的规则，不要复述原始样本。"
)

_EMPTY_SUMMARY = "话术库还是空的。去「教它」里教几条示范，我就能归纳出套路总纲了。"


def induce_summary(existing: str, samples: list[dict[str, Any]]) -> str:
    if not samples:
        return existing or _EMPTY_SUMMARY
    body = "\n\n".join(
        f"{i + 1}. 客户问题：{s['question']}\n"
        f"   标准答案：{s['answer']}\n"
        f"   这么答的原因/套路：{s.get('note') or '（未填）'}"
        for i, s in enumerate(samples)
    )
    if existing.strip():
        messages = [
            {"role": "system", "content": _MERGE_SYSTEM},
            {"role": "user", "content":
                "【现有套路总纲（店长已改写，须保留）】\n" + existing.strip()
                + "\n\n【新增教学样本】\n" + body},
        ]
    else:
        messages = [
            {"role": "system", "content": _INDUCE_SYSTEM},
            {"role": "user", "content": "以下是全部示范样本：\n\n" + body},
        ]
    decision = build_provider().chat(messages, [])   # 不传 tools，纯文本归纳
    return _clean_summary((decision.content or "").strip()) or existing or _EMPTY_SUMMARY


_META_LINE = re.compile(
    r"^\s*(#+\s*)?(【?(更新后的?|修订后的?|新的)?(套路)?总纲】?[：:]?|以下是.{0,20}[：:]?|好的[，,]\s*)$"
)


def _clean_summary(text: str) -> str:
    """去掉模型爱加的"【更新后的套路总纲】"这类抬头，只留正文。"""
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    while lines and (not lines[0].strip() or _META_LINE.match(lines[0])
                     or lines[0].strip().startswith("#")):
        lines.pop(0)
    return "\n".join(lines).strip()


_UPTODATE_KEY = "summary_upto_id"


def _get_upto() -> int:
    from ..db import cursor
    with cursor() as cur:
        cur.execute("SELECT value FROM settings WHERE key=?", (_UPTODATE_KEY,))
        row = cur.fetchone()
    try:
        return int(row["value"]) if row else 0
    except (TypeError, ValueError):
        return 0


def _set_upto(v: int) -> None:
    from ..db import cursor
    with cursor() as cur:
        cur.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (_UPTODATE_KEY, str(v)))


def refresh_summary(force_all: bool = False, rebuild: bool = False) -> dict[str, Any]:
    """重新归纳总纲。

    - 默认：增量（只喂"上次归纳之后新增的样本"），并保留店长手改的内容（状态合并）
    - force_all：把全部样本重喂一遍，但仍以现有总纲为基底
    - rebuild：**丢掉现有总纲，纯从当前样本重建**（样本删了、总纲要跟着消失时用）
    """
    existing = "" if rebuild else settings_service.get_summary()
    all_samples = playbook_service.recall_all_approved()
    upto = 0 if (force_all or rebuild) else _get_upto()
    fresh = [s for s in all_samples if s["id"] > upto] if existing else all_samples

    if not fresh and existing:
        return {"changed": False, "summary": existing, "used": 0,
                "added": [], "removed": []}

    new_summary = induce_summary(existing, fresh or all_samples)
    prev = settings_service.get_summary()
    settings_service.set_summary(new_summary)
    if all_samples:
        _set_upto(max(s["id"] for s in all_samples))

    added, removed = diff_summary(prev, new_summary)
    return {"changed": new_summary != prev, "summary": new_summary,
            "used": len(fresh or all_samples), "added": added, "removed": removed}


def diff_summary(old: str, new: str) -> tuple[list[str], list[str]]:
    """按行做差集，用于前端展示「这次总纲多了哪几条」。"""
    def norm(lines: list[str]) -> list[str]:
        return [ln.strip() for ln in (lines or []) if ln.strip()]

    old_lines = set(norm((old or "").splitlines()))
    new_lines = set(norm((new or "").splitlines()))
    added = [ln for ln in norm((new or "").splitlines()) if ln not in old_lines]
    removed = [ln for ln in norm((old or "").splitlines()) if ln not in new_lines]
    return added, removed


# ---------------------------------------------------------------- 提示词拼装

def effective_system_prompt() -> str:
    """四层拼装：技术流程 → 业务铁律 → 套路总纲 → 合规红线。

    每轮实时从库里读，所以店长改完总纲，下一句话就生效（不需要重启）。
    """
    parts = [BASE_PROMPT]
    parts.append(
        "\n\n【业务铁律（店长在后台可改，始终优先遵守，为最高规则）】\n"
        + settings_service.get_directive()
    )

    summary = settings_service.get_summary().strip()
    if summary:
        parts.append(
            "\n\n【套路总纲（店长已确认的应答策略，按此执行；"
            "recall_playbook 取到的样本只作具体话术参考，与本总纲冲突时以本总纲为准）】\n"
            + summary
        )

    banned = "、".join(config.COMPLIANCE_BANNED[:10])
    parts.append(
        "\n\n【合规红线（违反即事故）】\n"
        f"严禁出现这些说法：{banned}。\n"
        "严禁承诺具体工期、严禁承诺「绝对不会出问题」、严禁评价或贬低同行。"
    )
    return "".join(parts)
