"""同小区完工案例（演示数据）。

用途：客户报出小区后，给一个"隔壁邻居就是这么做的"实例，转化率最高。
同样只有区间，没有单点精确价。
"""

CASES = [
    {"community": "中海城", "layout": "三室两厅", "area": 118, "scenario": "全屋智能",
     "cost_min": 28000, "cost_max": 33000,
     "highlight": "灯控+窗帘+门锁+温控",
     "quote": "业主说最满意的是回家自动开灯开窗帘，老人也会用。"},
    {"community": "中海城", "layout": "四室两厅", "area": 143, "scenario": "全屋智能",
     "cost_min": 52000, "cost_max": 61000,
     "highlight": "加了安防和背景音乐",
     "quote": "家里有小孩，最看重的是门窗传感器和摄像头。"},
    {"community": "万科城", "layout": "三室一厅", "area": 96, "scenario": "灯光",
     "cost_min": 9000, "cost_max": 13000,
     "highlight": "无主灯 + 全屋调光",
     "quote": "预算有限就先把灯光做了，后面再补窗帘。"},
    {"community": "万科城", "layout": "两室一厅", "area": 78, "scenario": "安防",
     "cost_min": 6500, "cost_max": 9000,
     "highlight": "门锁 + 猫眼 + 2 路摄像头",
     "quote": "两口子上班不在家，装完心里踏实多了。"},
    {"community": "保利香槟", "layout": "三室两厅", "area": 128, "scenario": "全屋智能",
     "cost_min": 36000, "cost_max": 45000,
     "highlight": "全屋灯控 + 电动窗帘 + 场景面板",
     "quote": "女主人特别喜欢'一键离家'，出门不用挨个关灯。"},
    {"community": "龙湖天街", "layout": "四室两厅", "area": 165, "scenario": "影音",
     "cost_min": 26000, "cost_max": 32000,
     "highlight": "客厅影音 + 一键观影模式",
     "quote": "周末在家看电影，比去影院还舒服。"},
    {"community": "华润橡树湾", "layout": "三室两厅", "area": 112, "scenario": "全屋智能",
     "cost_min": 26000, "cost_max": 31000,
     "highlight": "舒适版标准配置",
     "quote": "和邻居一起做的，两家一起省了一笔安装费。"},
    {"community": "碧桂园凤凰城", "layout": "两室两厅", "area": 86, "scenario": "灯光",
     "cost_min": 8500, "cost_max": 11000,
     "highlight": "客餐厅无主灯",
     "quote": "预算两万以内，先把最想要的灯光做了。"},
]


def all_cases() -> list[dict]:
    return CASES
