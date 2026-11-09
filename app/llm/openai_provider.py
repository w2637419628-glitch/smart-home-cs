"""OpenAI 兼容的 LLM 提供方。

适配 DeepSeek / 火山引擎豆包 / 任意 OpenAI 兼容网关：
只改 .env 里的 base_url + model 即可，Loop 与工具不用动。

内部消息结构（assistant 带 tool_calls、tool 带 tool_call_id）与 OpenAI 的
function calling 结构几乎同构，这里只做格式映射，不做语义转换。
"""
from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from .base import LLMDecision, LLMProvider, ToolCall
from .. import config


class OpenAICompatProvider(LLMProvider):
    def __init__(self) -> None:
        if not config.LLM_API_KEY:
            raise RuntimeError(
                "未配置 LLM_API_KEY（或 DEEPSEEK_API_KEY），请在 .env 里填写。"
            )
        # timeout/max_retries 收紧：体验站不能让一个卡住的请求把页面拖死
        self.client = OpenAI(api_key=config.LLM_API_KEY,
                             base_url=config.LLM_BASE_URL,
                             timeout=30.0, max_retries=1)
        self.model = config.LLM_MODEL

    def chat(self, messages: list[dict[str, Any]],
             tools: list[dict[str, Any]]) -> LLMDecision:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": _to_openai_messages(messages),
            "temperature": config.LLM_TEMPERATURE,
        }
        if tools:  # 无工具场景（如归纳总纲）不传 tools，避免部分接口报错
            kwargs["tools"] = _to_openai_tools(tools)
            kwargs["tool_choice"] = "auto"

        resp = self.client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        thought = (msg.content or "").strip()

        if msg.tool_calls:
            calls: list[ToolCall] = []
            for c in msg.tool_calls:
                try:
                    args = json.loads(c.function.arguments or "{}")
                except (json.JSONDecodeError, TypeError):
                    args = {}
                calls.append(ToolCall(id=c.id, name=c.function.name, input=args))
            names = "、".join(c.name for c in calls)
            return LLMDecision(type="tool_call", tool_calls=calls,
                               thought=thought or f"调用工具 {names}。")

        return LLMDecision(type="final", thought=thought, content=msg.content or "")


def _to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t.get("parameters", {"type": "object", "properties": {}}),
        },
    } for t in tools]


def _to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if role in ("system", "user"):
            out.append({"role": role, "content": m.get("content") or ""})
        elif role == "assistant":
            tcs = m.get("tool_calls")
            if tcs:
                out.append({
                    "role": "assistant",
                    "content": m.get("content") or "",
                    "tool_calls": [{
                        "id": c["id"], "type": "function",
                        "function": {
                            "name": c["name"],
                            "arguments": json.dumps(c.get("input") or {}, ensure_ascii=False),
                        },
                    } for c in tcs],
                })
            else:
                out.append({"role": "assistant", "content": m.get("content") or ""})
        elif role == "tool":
            out.append({
                "role": "tool",
                "tool_call_id": m.get("tool_call_id"),
                "content": json.dumps(m.get("result"), ensure_ascii=False),
            })
    return out
