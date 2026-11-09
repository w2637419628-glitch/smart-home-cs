"""智能家居方案套餐（演示数据）。

⚠️ 重要：这里只有「区间」，没有精确总价。
价格红线是物理层面保证的——不存在 total_price 字段，模型想报总价也拿不到数。
"""

PACKAGES = [
    {
        "code": "P-LIGHT",
        "name": "智慧灯光包",
        "tier": "入门",
        "scenario": "灯光",
        "price_min": 8000, "price_max": 15000,
        "area_min": 60, "area_max": 130,
        "includes": "全屋调光模块、灯带、场景面板、网关、APP 与语音控制",
        "excludes": "灯具本体、开槽布线",
        "duration_days": 2,
        "highlight": "无主灯改造最省事的一档，先做这一个空间也能用",
    },
    {
        "code": "P-COMFORT",
        "name": "全屋智能·舒适版",
        "tier": "主流",
        "scenario": "全屋智能",
        "price_min": 25000, "price_max": 38000,
        "area_min": 80, "area_max": 140,
        "includes": "灯控、电动窗帘、智能门锁、温控、网关、APP 与语音控制",
        "excludes": "安防摄像头、背景音乐",
        "duration_days": 3,
        "highlight": "大多数三居家庭选这一档，性价比最高",
    },
    {
        "code": "P-PREMIUM",
        "name": "全屋智能·尊享版",
        "tier": "高端",
        "scenario": "全屋智能",
        "price_min": 50000, "price_max": 78000,
        "area_min": 120, "area_max": 220,
        "includes": "舒适版全部 + 安防（门锁猫眼摄像头）+ 背景音乐 + 场景联动编排",
        "excludes": "独立影音室声学改造",
        "duration_days": 5,
        "highlight": "大平层 / 别墅常用，联动场景可以按生活习惯定制",
    },
    {
        "code": "P-SECURITY",
        "name": "安防守护包",
        "tier": "入门",
        "scenario": "安防",
        "price_min": 6000, "price_max": 12000,
        "area_min": 50, "area_max": 999,
        "includes": "智能门锁、可视猫眼、2 路摄像头、门窗传感器、异常推送",
        "excludes": "墙体布线改造、云存储年费",
        "duration_days": 1,
        "highlight": "有老人小孩的家庭首选，装完当天就能用",
    },
    {
        "code": "P-AV",
        "name": "影音娱乐包",
        "tier": "进阶",
        "scenario": "影音",
        "price_min": 18000, "price_max": 35000,
        "area_min": 15, "area_max": 60,
        "includes": "5.1 声道音响、投影与幕布、声学处理、一键观影场景",
        "excludes": "吊顶改造、隔音墙",
        "duration_days": 3,
        "highlight": "独立影音间或客厅改造都能做，验收现场调音",
    },
]


def all_packages() -> list[dict]:
    return PACKAGES
