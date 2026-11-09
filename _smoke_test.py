# -*- coding: utf-8 -*-
"""端到端冒烟测试（走 HTTP，验证真实服务）。

用法：
    1) 另开一个窗口：python run.py
    2) python _smoke_test.py

自清理：跑完会删掉本次教进去的样本、把总纲恢复原样，可以反复跑。
"""
import json
import re
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8100"
SID = "smoke"

_RANGE_RE = re.compile(r"\d+(?:\.\d+)?\s*万?\s*(?:到|–|-|~|至)\s*\d+(?:\.\d+)?\s*万")


def call(path, payload=None, method="POST"):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


def chat(msg, sid=SID):
    r = call("/api/chat", {"message": msg, "session_id": sid})
    tools = [s["tool"] for s in r["trace"] if s["type"] == "tool_call"]
    print(f"\nQ: {msg}")
    print(f"   工具链: {tools}")
    print(f"   handoff={r['handoff']} survey={r.get('survey_id')} "
          f"需求 {r['slots_filled']}/{r['slots_total']}")
    print(f"   A: {r['reply']}")
    return r


def is_range(text: str) -> bool:
    """判断回复里是不是给了"区间"而不是一个精确价（兼容模型不同措辞）。"""
    return "区间" in text or bool(_RANGE_RE.search(text))


def main():
    created_sample_id = None
    before_summary = call("/api/summary", method="GET")["summary"]

    try:
        print("=" * 72)
        print("第一幕 · 一上来就问价 —— 不能报数字，必须先问")
        call("/api/session/reset?session_id=" + SID)
        r = chat("120平毛坯，想做全屋智能，大概多少钱？")
        assert "元" not in r["reply"] and "万" not in r["reply"], "第一句就报价了！"
        assert r["slots_filled"] >= 1, "没记录需求"

        print("\n第二幕 · 补齐需求（AI 一次只问一两项）")
        chat("三室两厅")
        r = chat("中海城，预算3万左右")
        assert r["slots_filled"] == r["slots_total"], f"需求没补齐：{r['lead']}"
        tools = [s["tool"] for s in r["trace"] if s["type"] == "tool_call"]
        assert "package_search" in tools and "case_search" in tools, \
            "同一轮没串起查套餐+查案例"
        assert is_range(r["reply"]), f"没给区间：{r['reply'][:80]}"

        print("\n第三幕 · 约上门勘测")
        r = chat("那你们能安排人上门看看吗？我电话13800001111")
        assert r["survey_id"], "没约成勘测"
        assert not r["handoff"], "高意向客户不该转人工"

        print("\n第四幕 · 问一个策略不允许答的（结构安全）→ 转人工 + 建工单")
        call("/api/session/reset?session_id=smoke_unlearned")
        r = chat("你们能改燃气管道吗？", sid="smoke_unlearned")
        assert r["handoff"] and r["ticket_id"], "没转人工"
        ticket_id = r["ticket_id"]

        print("\n第五幕 · 店长补答案 → 待审 → 通过 → 自动固化")
        out = call(f"/api/tickets/{ticket_id}/teach",
                   {"answer": "燃气管道不能私自改，得先报燃气公司审批。我们只能配合做柜体开孔和收口。",
                    "note": "涉及燃气安全一律不承诺能改，先讲要报批，把边界说清楚。"})
        created_sample_id = out["sample_id"]
        assert out["status"] == "pending", "应进待审"

        r2 = chat("你们能改燃气管道吗？", sid="smoke_unlearned2")
        assert r2["handoff"], "待审样本不该生效"

        ap = call(f"/api/playbook/{created_sample_id}/approve")
        print(f"   审核通过 → 总纲变化: {ap.get('summary_changed')}")
        after = call("/api/summary", method="GET")["summary"]
        assert after != before_summary, "总纲没变（自动固化失败）"

        prompt = call("/api/settings/system-prompt", method="GET")["prompt"]
        assert "燃气" in prompt, "新教的没进系统提示词"

        print("\n第六幕 · 同一问题再问 → 直接答对（不再转人工）")
        r3 = chat("你们能改燃气管道吗？", sid="smoke_unlearned3")
        assert not r3["handoff"], "教过了还在转人工"
        assert "燃气" in r3["reply"] or "审批" in r3["reply"], "没按教的答"

        print("\n第七幕 · 看板")
        for k, v in call("/api/metrics", method="GET").items():
            print(f"   {k}: {v}")

        print("\n" + "=" * 72)
        print("ALL PASSED ✅")

    finally:
        # 自清理：删样本 + 从剩余样本重建总纲（否则原理还留在总纲里，会污染下一轮）
        if created_sample_id:
            try:
                call(f"/api/playbook/{created_sample_id}", method="DELETE")
            except urllib.error.HTTPError:
                pass
        try:
            call("/api/summary/refresh?rebuild=true", method="POST")
        except urllib.error.HTTPError:
            call("/api/summary", {"text": before_summary}, method="PUT")
        for s in (SID, "smoke_unlearned", "smoke_unlearned2", "smoke_unlearned3"):
            call("/api/session/reset?session_id=" + s)
        print("（已清理本次教学产生的样本，并重建总纲，环境已还原）")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, urllib.error.URLError) as e:
        print("\n❌ FAILED:", e)
        sys.exit(1)
