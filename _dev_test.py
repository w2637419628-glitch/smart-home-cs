# -*- coding: utf-8 -*-
"""开发期直连测试（不启服务器，直接调 service）。用法：python _dev_test.py

自清理：跑完会把本次教进去的样本删掉、总纲恢复原样，
所以可以反复跑，不会污染演示环境。
"""
import os
import sys
import tempfile
from pathlib import Path

# 用独立的测试库，绝不碰演示用的 data.db
os.environ.setdefault("DSH_DB_PATH",
                      str(Path(tempfile.gettempdir()) / "smart_home_cs_test.db"))

from app import config  # noqa: E402
from app.db import init_db  # noqa: E402
from app.services import (chat_service, coach_service, lead_service,  # noqa: E402
                          playbook_service, review_service, settings_service)


def show(tag, r):
    print(f"  tools={r.tools_used} handoff={r.handoff} survey={r.survey_id}")
    print(f"  A: {r.reply}")


def main():
    init_db()
    playbook_service.seed_if_empty()

    created_sample_id = None
    before_summary = settings_service.get_summary()

    try:
        print("=" * 70)
        print("第一幕：客户一上来就问价 —— 不能报价，必须先问")
        sid = "smoke"
        chat_service.reset_session(sid)
        all_tools: set[str] = set()

        r = chat_service.handle_chat("120平毛坯，想做全屋智能，大概多少钱？", sid)
        all_tools |= set(r.tools_used)
        show("T1", r)
        assert "万" not in r.reply and "元" not in r.reply, "第一句就报价了！"

        print("\n第二幕：补齐需求")
        r = chat_service.handle_chat("三室两厅", sid)
        all_tools |= set(r.tools_used)
        show("T2", r)
        r = chat_service.handle_chat("中海城，预算3万左右", sid)
        all_tools |= set(r.tools_used)
        show("T3", r)
        assert "package_search" in r.tools_used and "case_search" in r.tools_used, \
            "同一轮没串起查套餐+查案例"

        lead = lead_service.get(sid)
        print("  LEAD:", {k: v for k, v in lead.items() if v and k in config.SLOT_KEYS})
        assert lead_service.filled_count(lead) == len(config.SLOT_KEYS), "槽位没补齐"

        print("\n第三幕：串工具 + 约勘测")
        r = chat_service.handle_chat("那你们能安排人上门看看吗？我电话13800001111", sid)
        all_tools |= set(r.tools_used)
        show("T4", r)
        assert {"package_search", "case_search", "book_survey"} <= all_tools, \
            f"工具链不完整：{all_tools}"
        assert r.survey_id, "没约成勘测"

        print("\n第四幕：问一个策略不允许答的（结构安全）→ 转人工")
        fresh_sid = "smoke_unlearned"
        chat_service.reset_session(fresh_sid)
        r = chat_service.handle_chat("你们能改燃气管道吗？", fresh_sid)
        show("T5", r)
        assert r.handoff and r.ticket_id, "没转人工"
        ticket_id = r.ticket_id

        print("\n第五幕：店长补答案 → 待审 → 通过 → 自动固化总纲")
        out = review_service.teach_from_ticket(
            ticket_id,
            "燃气管道不能私自改，得先报燃气公司审批。我们只能配合做柜体开孔和收口。",
            "涉及燃气安全一律不承诺能改，先讲要报批。")
        created_sample_id = out["sample_id"]
        print("  入库:", out)
        assert out["status"] == "pending", "应进待审"

        # 待审时不应该被检索到
        r2 = chat_service.handle_chat("你们能改燃气管道吗？", "smoke_unlearned2")
        print("  [待审阶段再问] handoff =", r2.handoff)
        assert r2.handoff, "待审样本不应生效"

        # 通过 → 自动固化
        playbook_service.approve_sample(created_sample_id)
        res = coach_service.refresh_summary()
        print(f"  总纲更新: changed={res['changed']} used={res['used']} "
              f"新增 {len(res['added'])} 行")
        assert res["changed"], "总纲没有变化"
        prompt = coach_service.effective_system_prompt()
        assert "燃气" in prompt, "新教的没进系统提示词"

        print("\n第六幕：同一问题再问 → 应该直接答对（不再转人工）")
        r3 = chat_service.handle_chat("你们能改燃气管道吗？", "smoke_unlearned3")
        show("T6", r3)
        assert not r3.handoff, "教过了还在转人工"

        print("\n第七幕：看板")
        for k, v in review_service.metrics().items():
            print(f"  {k}: {v}")

        print("\n" + "=" * 70)
        print("ALL PASSED ✅")

    finally:
        # 自清理：删样本 + 从剩余样本重建总纲
        if created_sample_id:
            playbook_service.delete_sample(created_sample_id)
            coach_service.refresh_summary(rebuild=True)
        for s in ("smoke", "smoke_unlearned", "smoke_unlearned2", "smoke_unlearned3"):
            chat_service.reset_session(s)
        print("（已清理本次教学产生的样本并重建总纲）")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print("\n❌ FAILED:", e)
        sys.exit(1)
