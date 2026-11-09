"""对话服务：维护会话、驱动 Agent Loop、做合规兜底、记指标。"""
from __future__ import annotations

import re
from typing import Any

from .. import config
from ..agent.loop import AgentLoop, LoopResult
from ..db import cursor
from ..llm.factory import build_provider
from . import coach_service, lead_service

# 进程内会话存储（演示够用；生产换 Redis / DB）
_SESSIONS: dict[str, list[dict[str, Any]]] = {}
_MAX_HISTORY_MESSAGES = 24

_LOOP = AgentLoop(build_provider())

_PRICE_RE = [re.compile(p) for p in config.PRICE_BANNED_PATTERNS]
_FALLBACK_REPLY = (
    "这个我这边不方便直接给准数，得让顾问按您家实际情况算一下。"
    "您留个电话，我帮您约个免费勘测，现场出方案更靠谱。"
)

# 模型"嘴上说转人工、实际没调 handoff"的兜底识别
_TRANSFER_RE = re.compile(
    r"转(?:接)?人工|转给(?:人工|顾问)|让(?:懂|专业|人工)?顾问(?:跟|和|给)您|"
    r"顾问(?:会)?跟您(?:确认|联系|对接)|专人和您(?:联系|确认)|人工顾问(?:跟|和)您"
)

# 硬承诺：具体工期 / 绝对化 / 保证类。这些即使有"常见技术可做"的授权，也不能说。
# 注意：泛化的"能做"是被铁律第 6 条授权过的，不在此拦截范围内。
_HARD_CLAIM_RE = re.compile(
    r"保证|绝对|100%|百分百|包过|包您满意|零风险|绝不会|"
    r"(\d+|[一二三四五六七八九十两]+)\s*(天|个?工作日|小时)\s*(内|完工|装完|搞定|上门)|"
    r"当天(?:完工|装完|到货)|明天(?:到|装)"
)
_SAFE_REWRITE = (
    "工艺上没问题，但具体能做到什么程度、要多久，得让懂工艺的顾问看现场给您准话。"
    "已经帮您转给顾问了，稍后有人跟您对接。"
)


def effective_system_prompt() -> str:
    return coach_service.effective_system_prompt()


def handle_chat(message: str, session_id: str = "demo") -> LoopResult:
    lead_service.get_or_create(session_id)

    # system 每轮重新拼（总纲/铁律改完立刻生效），会话里只存对话轮次
    history = _SESSIONS.get(session_id, [])

    try:
        result = _LOOP.run(message, history=history,
                           system=coach_service.effective_system_prompt(),
                           session_id=session_id)
    except Exception as exc:
        # 模型服务挂了 / 断网 / 超时 —— 绝不能把 500 抛给客户
        result = LoopResult(
            reply="抱歉，我这边的模型服务刚才断了，没听清您说的。"
                  "可以稍等几秒再发一次，或者我直接帮您转人工顾问。",
            trace=[{"step": 0, "type": "llm_error", "error": str(exc)[:300],
                    "note": "模型调用失败，已降级为友好提示"}],
            session_messages=list(history) + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": "(模型服务异常)"},
            ],
        )

    # 合规兜底：命中红线就改写，并把拦截原因留在轨迹里（可审计）
    guarded, reasons = guard_reply(result.reply)
    if reasons:
        result.trace.append({"step": 0, "type": "compliance_blocked",
                             "reasons": reasons,
                             "original": result.reply, "replaced": guarded})
        result.reply = guarded

    # 未覆盖问题的处理：
    #   店长在铁律里授权了"常见技术可以直接说能做"，所以泛化承诺放行（只留审计痕迹）；
    #   但只要出现"具体工期 / 绝对化 / 保证"这类硬承诺，一律拦下并转人工。
    if (not result.handoff) and (not result.survey_id) and (not result.playbook_covered):
        hard = _HARD_CLAIM_RE.search(result.reply or "")
        if hard:
            from . import review_service
            tid = review_service.open_ticket(
                session_id, message, f"(未学过却作了硬承诺「{hard.group(0)}」，系统拦截)")
            result.trace.append({"step": 0, "type": "hallucination_blocked",
                                 "ticket_id": tid, "matched": hard.group(0),
                                 "original": result.reply,
                                 "note": "套路库没覆盖又给了具体承诺，已改写并转人工"})
            result.reply = _SAFE_REWRITE
            result.handoff = True
            result.ticket_id = tid
        else:
            # 常见技术授权内的作答：放行，但留痕，便于事后抽查
            result.trace.append({"step": 0, "type": "uncovered_answered",
                                 "note": "套路库未覆盖，按「常见技术可做」铁律作答"})

    # 转人工兜底：模型嘴上说"让顾问跟您确认"，却没真的建工单 → 系统补建。
    # 没有这张工单，自进化的"工单补充"入口就断了，所以必须是硬保证。
    if (not result.handoff) and (not result.survey_id) \
            and _TRANSFER_RE.search(result.reply or ""):
        from . import review_service
        tid = review_service.open_ticket(
            session_id, message, "(模型口头转人工，系统自动补建工单)")
        result.handoff = True
        result.ticket_id = tid
        result.trace.append({"step": 0, "type": "ticket_autocreated",
                             "ticket_id": tid,
                             "note": "检测到回复里承诺转人工但未调用 handoff，已自动补建工单"})

    # 只把「用户消息 + 最终回复」落进上下文（剥离 tool 调用噪声）
    kept = [m for m in result.session_messages
            if m.get("role") == "user"
            or (m.get("role") == "assistant" and not m.get("tool_calls"))]
    _SESSIONS[session_id] = kept[-_MAX_HISTORY_MESSAGES:]

    _log_metrics(session_id, message, result)
    return result


def guard_reply(reply: str) -> tuple[str, list[str]]:
    """合规检查：违禁词 + 精确总价。命中就换成安全话术。"""
    reasons: list[str] = []
    text = reply or ""

    for w in config.COMPLIANCE_BANNED:
        if w in text:
            reasons.append(f"违禁说法：{w}")

    # 只拦"精确总价"，放过"区间"
    has_range = ("区间" in text) or ("–" in text) or ("-" in text and "万" in text)
    for rx in _PRICE_RE:
        if rx.search(text) and not has_range:
            reasons.append(f"精确总价：{rx.pattern}")

    return (_FALLBACK_REPLY if reasons else text), reasons


def reset_session(session_id: str = "demo") -> None:
    """重置会话：对话历史 + 客户档案都要清，否则进度条会带着上一轮的数据。"""
    _SESSIONS.pop(session_id, None)
    lead_service.reset(session_id)


def _log_metrics(session_id: str, question: str, result: LoopResult) -> None:
    lead = lead_service.get(session_id)
    hit = 1 if (result.playbook_hit and not result.handoff) else 0
    with cursor() as cur:
        cur.execute(
            "INSERT INTO metrics_log (session_id, question, playbook_hit, handoff, "
            "slots_filled, tools_used) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, question, hit, 1 if result.handoff else 0,
             lead_service.filled_count(lead), ",".join(result.tools_used)),
        )
