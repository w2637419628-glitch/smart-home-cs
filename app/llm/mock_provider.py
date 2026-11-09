"""离线规则桩（Mock 大脑）。

用途：没有网络 / 没有 API Key 时，也能完整演示 Agent Loop + 自进化闭环。
它不是"假装智能"——它读对话历史与工具返回，用规则模拟"该调哪个工具 / 该不该追问"。
接真实模型（OpenAICompatProvider）时，这套规则由模型自己判断，Loop 与工具一行不用改。
"""
from __future__ import annotations

import re
from typing import Any

from .base import LLMDecision, LLMProvider, ToolCall
from .. import config

# ---------------- 关键词表 ----------------

# 需求场景（顺序即优先级："全屋智能"优先于"灯光"）
SCENARIO_WORDS: list[tuple[str, list[str]]] = [
    ("全屋智能", ["全屋智能", "全屋", "整套", "智能家居", "全家"]),
    ("影音", ["影音", "音箱", "音响", "投影", "影院", "ktv"]),
    ("安防", ["安防", "监控", "摄像", "门锁", "报警", "猫眼"]),
    ("灯光", ["灯光", "照明", "灯带", "调光", "无主灯", "吸顶灯"]),
    ("窗帘", ["窗帘", "电动帘", "电动窗帘"]),
]

_PRICE_RE = re.compile(r"多少钱|价格|报价|贵不贵|费用|预算够|什么价|几万")
_BOOK_RE = re.compile(r"上门|勘测|量房|看现场|过来看|安排人|什么时候能来|约个时间")
_ASK_RE = re.compile(r"能|可以|支持|有没有|是否|吗|？|\?")
_GREET_RE = re.compile(r"^(在吗|在么|在不在|你好|您好|哈喽|hello|hi|有人吗|老板)[！!。.,，]?$", re.I)
_THANKS_RE = re.compile(r"^(谢谢|好的|好|嗯|行|可以|收到|辛苦了)[！!。.]?$")
_AREA_RE = re.compile(r"(\d{2,3})\s*(?:平|㎡|平米|平方米)")
_LAYOUT_RE = re.compile(r"([一二三四五六两\d])\s*[室居](?:([一二三四五六两\d])\s*厅)?")
_BUDGET_RE = re.compile(r"(\d+(?:\.\d+)?)\s*万")
_PHONE_RE = re.compile(r"(1[3-9]\d{9})")
_STAGE_WORDS = [("毛坯", ["毛坯", "毛坏", "刚交房", "新房"]),
                ("硬装中", ["硬装", "水电", "装修中", "正在装"]),
                ("已入住", ["已入住", "住进去了", "老房", "翻新"])]

_CN_NUM = {"一": "1", "二": "2", "两": "2", "三": "3", "四": "4", "五": "5", "六": "6"}
_BACK_CN = {"1": "一", "2": "两", "3": "三", "4": "四", "5": "五", "6": "六"}


def _call(name: str, tool_input: dict[str, Any], thought: str) -> LLMDecision:
    return LLMDecision(type="tool_call",
                       tool_calls=[ToolCall(id=f"call_{name}", name=name, input=tool_input)],
                       thought=thought)


def _final(content: str, thought: str = "") -> LLMDecision:
    return LLMDecision(type="final", thought=thought or "按已掌握的信息作答。", content=content)


def _last_user_message(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content", "") or ""
    return ""


def _tool_results_since_last_user(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """{tool_name: result} —— 本轮用户提问后已执行过的工具及结果。"""
    results: dict[str, Any] = {}
    collecting = False
    for m in messages:
        if m.get("role") == "user":
            results, collecting = {}, True
            continue
        if collecting and m.get("role") == "tool":
            results[m.get("name")] = m.get("result")
    return results


def _known_communities() -> list[str]:
    try:
        from ..data.cases import all_cases
        return [c["community"] for c in all_cases() if c.get("community")]
    except Exception:
        return []


def _extract_slots(q: str) -> dict[str, Any]:
    """从这句话里抽取需求槽位（只提到几项就抽几项）。"""
    slots: dict[str, Any] = {}
    text = q or ""

    for name, words in SCENARIO_WORDS:
        if any(w in text.lower() for w in words):
            slots["scenario"] = name
            break

    m = _AREA_RE.search(text)
    if m:
        slots["area"] = int(m.group(1))

    m = _LAYOUT_RE.search(text)
    if m:
        a = _CN_NUM.get(m.group(1), m.group(1))
        b = m.group(2)
        b = _CN_NUM.get(b, b) if b else None
        # 展示时用中文数字，和案例库口径一致
        a_cn = _BACK_CN.get(a, a)
        layout = f"{a_cn}室{_BACK_CN.get(b, b)}厅" if b else f"{a_cn}室"
        slots["layout"] = layout

    for label, words in _STAGE_WORDS:
        if any(w in text for w in words):
            slots["stage_reno"] = label
            break

    m = _BUDGET_RE.search(text)
    if m:
        slots["budget"] = f"{m.group(1)}万"

    m = _PHONE_RE.search(text)
    if m:
        slots["phone"] = m.group(1)

    for c in _known_communities():
        if c and c in text:
            slots["community"] = c
            break

    return slots


_SHORT = {
    "scenario": "想做哪一块", "area": "房子多大", "layout": "几室几厅",
    "stage_reno": "装修到哪一步", "budget": "预算多少", "community": "在哪个小区",
}


def _ask(slot: str, filled: dict[str, Any]) -> str:
    """针对缺失槽位的自然追问。"""
    scenario = filled.get("scenario")
    if slot == "scenario":
        return "行～先问一下，您是想做全屋智能，还是只做灯光 / 安防 / 影音其中一块？"
    if slot == "area":
        return "您房子建筑面积大概多少平？我好按面积给您算区间。"
    if slot == "layout":
        return "户型是几室几厅呀？不同户型布点差别挺大的。"
    if slot == "stage_reno":
        return "现在装修到哪一步了？毛坯、硬装中，还是已经入住了？"
    if slot == "budget":
        return f"您预算大概想控制在多少？（{scenario + '这块' if scenario else ''}我给的范围会比较准）"
    if slot == "community":
        return "在哪个小区呀？我看看有没有同小区的案例给您参考。"
    return "再多跟我说一点您的情况？"


class MockLLMProvider(LLMProvider):
    def chat(self, messages: list[dict[str, Any]],
             tools: list[dict[str, Any]]) -> LLMDecision:
        # 没有工具 = 纯文本归纳任务（生成/合并套路总纲）
        if not tools:
            return _final(_mock_summary(messages), "把样本里的原因归纳成通用原则。")

        q = _last_user_message(messages)
        done = _tool_results_since_last_user(messages)

        # ① 客户明确要人工
        if re.search(r"转人工|找人工|要人工|人工客服", q) and "handoff" not in done:
            return _call("handoff", {"question": q, "context": "客户主动要求人工"},
                         "客户明确要求人工，直接转接。")

        # ①.5 打招呼 / 客套 —— 不该触发转人工，直接接住话头
        if _GREET_RE.match(q.strip()):
            return _final("在的～您是想了解全屋智能，还是只做灯光／安防／影音其中一块？"
                          "方便再说下房子多大、现在装修到哪一步了吗？",
                          "客户只是打招呼，先热情接住并引导说需求。")
        if _THANKS_RE.match(q.strip()):
            return _final("不客气～有需要随时找我，也可以直接帮您约个免费上门勘测。",
                          "客户在收尾，礼貌回应并留一个下一步。")

        # ①.6 纯粹的语气词 / 标点（"？？？""哦""额"）—— 也算没听清，别转人工
        meaningful = re.sub(r"[^\w\u4e00-\u9fff]", "", q or "")
        if len(meaningful) <= 2 and not _extract_slots(q):
            return _final("您方便展开说说吗？比如想做哪一块、房子多大，我好给您算个数。",
                          "这句信息量太低，先请客户补充。")

        # ② 每轮第一步：召回店长教过的话术
        if "recall_playbook" not in done:
            return _call("recall_playbook", {"query": q},
                         "先看店长教过哪些类似的话术。")

        pb = done.get("recall_playbook") or {}
        samples = pb.get("samples") or []
        top_score = (samples[0].get("score", 0.0) if samples else 0.0)
        has_playbook = bool(pb.get("count"))

        slots = _extract_slots(q)
        price_ask = bool(_PRICE_RE.search(q))
        book_ask = bool(_BOOK_RE.search(q))
        ask_like = bool(_ASK_RE.search(q))

        need_dialog = bool(slots) or price_ask or book_ask

        # ③ 纯问答路径：没提到任何需求信息
        if not need_dialog:
            if "handoff" in done:
                return _final("这个问题我确实没把握，怕给您答错了，已经帮您转给人工顾问了，"
                              "稍后会有专人和您联系。")
            if has_playbook and top_score >= config.PLAYBOOK_HIT_THRESHOLD:
                return _final(_clean(samples[0].get("answer", "")),
                              "命中了店长教过的话术，直接按它的说法答。")
            if ask_like:
                return _call("handoff",
                             {"question": q, "context": "套路库里没有覆盖到这个问题"},
                             "这个问题我没学过，也不敢乱答，转人工。")
            if "save_requirements" not in done:
                return _call("save_requirements", {"slots": {}},
                             "先看看客户档案里还缺什么信息。")
            return _final("您方便再说具体一点吗？比如想做哪一块、房子多大，我好给您一个准数。",
                          "这句话里没有可用信息，先把话头接住。")

        # ④ 需求路径：先把这句话里提到的信息记进档案
        if "save_requirements" not in done:
            return _call("save_requirements", {"slots": slots},
                         "把客户这句话里提到的需求记到档案里。")

        req = done.get("save_requirements") or {}
        filled = req.get("slots") or {}
        missing = req.get("missing") or []

        # ⑤ 需求齐了 + 客户问上门 → 约勘测
        if book_ask and not missing:
            if "book_survey" not in done:
                return _call("book_survey",
                             {"community": filled.get("community", ""),
                              "layout": filled.get("layout", ""),
                              "area": filled.get("area", 0),
                              "phone": filled.get("phone", "")},
                             "需求已经问全，客户主动问上门，直接约免费勘测。")
            sv = done.get("book_survey") or {}
            if sv.get("survey_id"):
                return _final(
                    f"约好了！{filled.get('community') or ''}"
                    f"{filled.get('layout') or ''}".strip()
                    + f"，顾问会在 2 小时内电话跟您确认具体时间。"
                    "到场会现场量尺寸、看布线，然后给您出详细方案和准确区间。"
                )
            return _final("行，我给您约免费勘测。方便留个手机号吗？顾问会先电话跟您约时间。")

        # ⑥ 需求不全 → 绝不报价，先追问
        if missing:
            if price_ask:
                return _final("价格得看到具体方案才能算准，我不给您报虚数。先了解一下："
                              + _ask(missing[0], filled))
            if not slots:
                # 这一句没带来新信息，别把同一个问题再问一遍
                labels = [f"{_SHORT.get(m, m)}" for m in missing[:2]]
                return _final("咱们一项项来就行，我一次问完：" + "、".join(labels) + "？",
                              "没提取到新信息，换个问法把剩下的一起问。")
            return _final(_ask(missing[0], filled))

        # ⑦ 需求齐了 → 查套餐
        if "package_search" not in done:
            return _call("package_search",
                         {"scenario": filled.get("scenario", ""),
                          "area": filled.get("area", 0)},
                         "需求齐了，先查这个场景、这个面积对应的方案区间。")

        # ⑧ 再查同小区案例
        if "case_search" not in done:
            return _call("case_search",
                         {"community": filled.get("community", ""),
                          "layout": filled.get("layout", ""),
                          "scenario": filled.get("scenario", "")},
                         "配上同小区、同户型的真实案例，客户更容易信。")

        # ⑨ 收官
        return _final(_compose(filled, done, samples), "区间 + 案例 + 约勘测，一次给到位。")


def _clean(s: str) -> str:
    return re.sub(r"\s+", "", s or "").strip()


_HEADER_RULES = (
    "一、谈价：客户问价先问需求，只给区间，绝不报精确总价。\n"
    "二、异议：讲方案差异、调试与质保，不降价、不贬低同行。\n"
    "三、推进：需求问全就给区间 + 同小区案例，并约免费勘测。\n"
    "四、禁区：不承诺工期、不承诺绝对稳定、不站外交易。"
)


def _mock_summary(messages: list[dict[str, Any]]) -> str:
    """离线桩的"归纳"：从样本的原因里提炼条目，并保留店长已改写的部分。"""
    full = "\n".join((m.get("content") or "") for m in messages
                     if m.get("role") == "user")

    existing = ""
    m = re.search(r"【现有套路总纲（店长已改写，须保留）】\n(.*?)\n\n【", full, re.S)
    if m:
        existing = m.group(1).strip()

    reasons = re.findall(r"这么答的原因/套路：(.+)", full)
    principles: list[str] = []
    # 新教的排在前面：最近的样本先进总纲，这样才能"教完立刻看到变化"
    for r in reversed(reasons):
        head = re.split(r"[。；;，,]", r.strip())[0].strip()
        if head and head not in principles:
            principles.append(head)

    lines = [f"{i + 1}. {p}" for i, p in enumerate(principles[:8])]
    body = _HEADER_RULES
    if principles:
        body += "\n五、具体套路：\n" + "\n".join(lines)
    return (existing + "\n\n" + body).strip() if existing else body


def _compose(filled: dict[str, Any], done: dict[str, Any], samples: list[dict]) -> str:
    """把套餐区间 + 案例 + 邀约拼成一段人话（永不出现精确总价）。"""
    pkg = (done.get("package_search") or {}).get("package")
    cases = (done.get("case_search") or {}).get("cases") or []
    area = filled.get("area")
    scenario = filled.get("scenario") or "全屋智能"

    parts: list[str] = []
    parts.append(f"您{area:g}平的{scenario}，我给您说个实在的区间。" if area
                 else f"您想做的{scenario}，我给您说个实在的区间。")

    if pkg:
        lo = f"{pkg['price_min'] / 10000:g}万"
        hi = f"{pkg['price_max'] / 10000:g}万"
        parts.append(
            f"像您这种情况一般落在 {lo}–{hi} 这个区间（{pkg['includes']}；"
            f"不含{pkg['excludes']}），具体以现场勘测为准，不会给您报虚数。"
        )

    if cases:
        c = cases[0]
        parts.append(
            f"同小区{c['community']}一套{c['layout']}，做的也是{c['scenario']}，"
            f"实际花了{c['cost_min'] / 10000:g}万–{c['cost_max'] / 10000:g}万。"
            f"{c.get('quote', '')}"
        )

    parts.append("要不我先帮您约个免费上门勘测？现场量完给您出详细方案，比在这儿猜准得多。")
    return "".join(parts)
