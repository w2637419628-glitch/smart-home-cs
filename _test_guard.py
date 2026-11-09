# -*- coding: utf-8 -*-
"""验证 Agent Loop 的"防原地打转"护栏。

构造一个永远返回同一个 tool_call 的假模型，看 Loop 会不会：
  1) 第 3 次起不再真跑工具，而是回填 duplicate 错误；
  2) 最终收敛（不无限循环）。
"""
from app.agent.loop import AgentLoop
from app.llm.base import LLMDecision, LLMProvider, ToolCall

class StuckProvider(LLMProvider):
    """模拟"卡住"的模型：永远调同一个工具、同一份入参。"""

    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools):
        self.calls += 1
        return LLMDecision(
            type="tool_call",
            thought="我再查一次应该就有结果了。",
            tool_calls=[ToolCall(id="same", name="package_search",
                                 input={"scenario": "全屋智能", "area": 120})],
        )


def main():
    from app.db import init_db
    init_db()

    llm = StuckProvider()
    loop = AgentLoop(llm)
    r = loop.run("测试", session_id="guard")

    dup = [t for t in r.trace
           if t["type"] == "tool_result" and isinstance(t["output"], dict)
           and t["output"].get("duplicate")]
    print("模型被调用次数:", llm.calls)
    print("工具真实执行次数:", len([t for t in r.trace if t["type"] == "tool_call"]) - len(dup))
    print("被拦下的重复调用:", len(dup))
    print("最终回复:", r.reply)

    assert llm.calls <= 8, "Loop 没有收敛"
    assert dup, "护栏没生效（没有拦截重复调用）"
    print("\n护栏生效 ✅")


if __name__ == "__main__":
    main()
