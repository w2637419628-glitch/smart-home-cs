"""Agent Loop 引擎（本项目的心脏）。

一个 while 循环实现：推理 → 选工具 → 调用 → 观察结果 → 再决策 → 收尾。

三条设计原则：
1. 决策权完全交给模型——没有 if-else 的意图分类，工具选择即意图识别。
2. 错误即上下文——工具异常包装成 observation 回填，让模型自己纠正，不中断会话。
3. 确定性护栏——最大步数 + 超时双保险，超限降级转人工，保证服务可预期。
"""
from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field
from typing import Any

from .. import config
from ..llm.base import LLMProvider
from .tools import build_registry


@dataclass
class LoopResult:
    reply: str
    trace: list[dict[str, Any]] = field(default_factory=list)
    handoff: bool = False
    ticket_id: int | None = None
    survey_id: int | None = None
    playbook_hit: bool = False
    playbook_covered: bool = True
    tools_used: list[str] = field(default_factory=list)
    session_messages: list[dict[str, Any]] = field(default_factory=list)


class AgentLoop:
    def __init__(self, llm: LLMProvider):
        self.llm = llm
        self.tools = build_registry()

    def _tool_schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self.tools.values()]

    def run(self, user_message: str,
            history: list[dict[str, Any]] | None = None,
            system: str | None = None,
            session_id: str | None = None) -> LoopResult:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages += list(history or [])
        messages.append({"role": "user", "content": user_message})

        trace: list[dict[str, Any]] = []
        handoff = False
        ticket_id: int | None = None
        survey_id: int | None = None
        playbook_hit = False
        playbook_covered = True
        tools_used: list[str] = []

        started = time.time()
        step = 0
        seen: dict[str, int] = {}
        dup_streak = 0
        reply = "抱歉，系统忙不过来，我先帮您转人工。"

        while step < config.MAX_LOOP_STEPS:
            # 护栏一：超时
            if time.time() - started > config.LOOP_TIMEOUT_SECONDS:
                reply = "这个情况有点复杂，我先帮您转接人工顾问，稍后给您回电。"
                trace.append({"step": step, "type": "final",
                              "content": "(超时，边界护栏触发)"})
                break

            step += 1
            schemas = self._tool_schemas()

            # ① 调用前：记录完整上下文（调试"模型到底看到了什么"）
            trace.append({"step": step, "type": "llm_call",
                          "messages": copy.deepcopy(messages),
                          "available_tools": [t["name"] for t in schemas]})

            decision = self.llm.chat(messages, schemas)

            # ② 返回后：记录原始决策（调试"模型决定干什么"）
            trace.append({"step": step, "type": "llm_response",
                          "decision": decision.type,
                          "thought": decision.thought,
                          "tool_calls": [{"id": c.id, "name": c.name, "input": c.input}
                                         for c in decision.tool_calls],
                          "content": decision.content})
            if decision.thought:
                trace.append({"step": step, "type": "think", "content": decision.thought})

            if decision.type == "final":
                reply = decision.content or ""
                trace.append({"step": step, "type": "final", "content": reply})
                messages.append({"role": "assistant", "content": reply})
                break

            # tool_calls：本步可并行多个（按标准 assistant → tool 配对记录）
            calls = decision.tool_calls
            messages.append({
                "role": "assistant",
                "content": decision.thought or "",
                "tool_calls": [{"id": c.id, "name": c.name, "input": c.input} for c in calls],
            })

            for call in calls:
                tools_used.append(call.name)
                trace.append({"step": step, "type": "tool_call",
                              "tool": call.name, "input": call.input})

                # 防原地打转：同一个工具 + 同一份入参，最多真跑 2 次。
                # 第 3 次起不再执行，而是回填一条错误观测，让模型自己纠正。
                sig = call.name + "|" + json.dumps(call.input or {}, sort_keys=True,
                                                   ensure_ascii=False)
                seen[sig] = seen.get(sig, 0) + 1
                if seen[sig] > 2:
                    result = {
                        "error": f"你已经用完全相同的参数调用过 {call.name} 两次了，"
                                 "结果不会变。请直接基于已有结果作答，或换一种方式。",
                        "duplicate": True,
                    }
                    tool = None
                    already = True
                else:
                    already = False
                    tool = self.tools.get(call.name)

                if not already:
                    try:
                        if tool is None:
                            result = {"error": f"未知工具：{call.name}"}
                        else:
                            # 注入会话上下文（工具用它读写客户档案），模型传的同名参数优先
                            payload = {"session_id": session_id, **(call.input or {})}
                            result = tool.run(**payload)
                    except Exception as exc:  # 工具异常 → observation，让模型自己纠错
                        result = {"error": f"工具 {call.name} 执行出错：{exc}"}

                is_error = isinstance(result, dict) and "error" in result
                trace.append({"step": step, "type": "tool_result",
                              "tool": call.name, "output": result, "is_error": is_error})
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "name": call.name, "result": result})

                # 旁路信号（用于指标与返回）
                if call.name == "handoff" and isinstance(result, dict) and result.get("ticket_id"):
                    handoff = True
                    ticket_id = result.get("ticket_id")
                if call.name == "book_survey" and isinstance(result, dict) and result.get("survey_id"):
                    survey_id = result.get("survey_id")
                if call.name == "recall_playbook" and isinstance(result, dict):
                    playbook_hit = playbook_hit or bool(result.get("count"))
                    # "店长教没教过"——没覆盖的，事后要检查模型是不是在瞎答
                    playbook_covered = bool(result.get("covered", True))
                if isinstance(result, dict) and result.get("duplicate"):
                    dup_streak += 1

            # 模型连着两次都在原地打转 → 别再烧步数，直接收尾兜底
            if dup_streak >= 2:
                reply = ("我这边好像一直没取到新信息，别耽误您时间 —— "
                         "我把您的需求记下来了，让顾问直接跟您对接更稳妥。")
                trace.append({"step": step, "type": "final",
                              "content": "(模型重复调用同一工具，护栏提前收尾)"})
                break
        else:
            # 护栏二：达到最大步数仍未收尾
            reply = "这个我得让顾问跟您细聊，我先帮您转接人工。"
            trace.append({"step": step, "type": "final",
                          "content": "(达到最大循环步数，边界护栏触发)"})

        return LoopResult(reply=reply, trace=trace, handoff=handoff,
                          ticket_id=ticket_id, survey_id=survey_id,
                          playbook_hit=playbook_hit,
                          playbook_covered=playbook_covered,
                          tools_used=tools_used,
                          session_messages=messages)
