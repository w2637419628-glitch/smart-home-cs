"""公网体验模式的额度控制。

为什么需要：体验站是**公开链接**，谁都能点。每次对话都要花真实的模型 API 费用，
不加限制的话，一个爬虫或一个好奇的人连点一百次，你的余额就没了。

两道闸：
  · 单 IP 每天最多 N 次（防止一个人狂点）
  · 全局每天最多 M 次（防止总量失控）

计数存在进程内存里，跨天自动清零。重启会清零——对体验站来说可以接受。
"""
from __future__ import annotations

import threading
from datetime import date

from .. import config

_lock = threading.Lock()
_day: date = date.today()
_per_ip: dict[str, int] = {}
_global_count: int = 0


def _roll_if_new_day() -> None:
    global _day, _per_ip, _global_count
    today = date.today()
    if today != _day:
        _day = today
        _per_ip = {}
        _global_count = 0


def check_and_consume(ip: str) -> tuple[bool, str]:
    """返回 (是否放行, 提示语)。放行时会先扣一次额度。"""
    if not config.DEMO_MODE:
        return True, ""

    global _global_count
    with _lock:
        _roll_if_new_day()

        if config.DEMO_GLOBAL_DAILY and _global_count >= config.DEMO_GLOBAL_DAILY:
            return False, (
                "今天的体验额度已经用完了（全站上限）。"
                "想看完整演示可以联系我，或者明天再来～"
            )

        used = _per_ip.get(ip, 0)
        if config.DEMO_PER_IP_DAILY and used >= config.DEMO_PER_IP_DAILY:
            return False, (
                f"您今天的体验次数（{config.DEMO_PER_IP_DAILY} 次）已经用完了。"
                "这个额度是为了让更多人也能试用，明天会重置～"
            )

        _per_ip[ip] = used + 1
        _global_count += 1
        return True, ""


def snapshot() -> dict:
    """给看板/状态接口用。"""
    with _lock:
        _roll_if_new_day()
        return {
            "demo_mode": config.DEMO_MODE,
            "global_used": _global_count,
            "global_limit": config.DEMO_GLOBAL_DAILY,
            "per_ip_limit": config.DEMO_PER_IP_DAILY,
            "distinct_ips": len(_per_ip),
        }
