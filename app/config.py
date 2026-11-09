"""全局配置。

所有可调项集中在这里，方便演示时改（不需要改代码逻辑）。
"""
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# 测试可以用 DSH_DB_PATH 指向独立的库，避免污染演示数据
DB_PATH = Path(os.getenv("DSH_DB_PATH") or (BASE_DIR / "data.db"))

# 从项目根 .env 读取密钥（没有这个文件也不会报错）
load_dotenv(BASE_DIR / ".env")

APP_NAME = "会进化的智能家居客服"
APP_TAGLINE = "Agent Loop · 边聊边学 · 自动固化"

# ---------- Agent Loop 边界控制 ----------
MAX_LOOP_STEPS = 8          # 单次对话最多循环步数（本场景工具更多，比原来的 6 放宽）
LOOP_TIMEOUT_SECONDS = 45   # 单次对话超时

# ---------- 语义检索 ----------
PLAYBOOK_TOP_K = int(os.getenv("PLAYBOOK_TOP_K", "4"))
# 套路命中阈值：低于此值视为"没学过"，交给模型判断是否转人工。
# 用本地 IDF 词法后端时建议 0.25 左右；换成 ARK 真向量后可调到 0.5。
PLAYBOOK_HIT_THRESHOLD = float(os.getenv("PLAYBOOK_HIT_THRESHOLD", "0.25"))

# ---------- 大模型 ----------
# mock = 离线规则桩；openai = 任意 OpenAI 兼容接口（DeepSeek / 豆包 / 通义…）
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))

# 让模型域名绕过系统代理。
# 原因：Windows 上 Python（urllib/openai）会自动读取注册表里的系统代理，
# 如果本机代理软件没开、但代理设置还留着，TLS 握手会直接失败
# （报 SSL: UNEXPECTED_EOF_WHILE_READING），表现为"模型服务断线"。
# DeepSeek 是国内接口，本来就不该走代理。
try:
    _host = urlparse(LLM_BASE_URL).hostname
    if _host:
        _np = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
        if _host not in _np:
            _np = ",".join(x for x in (_np, "127.0.0.1", "localhost", _host) if x)
            os.environ["NO_PROXY"] = _np
            os.environ["no_proxy"] = _np
except Exception:
    pass

# ---------- Embedding ----------
# 恒可用：本地特征哈希（离线）；配了 ARK 就优先用真向量
ARK_API_KEY = os.getenv("ARK_API_KEY", "")
ARK_BASE_URL = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
ARK_EMBED_MODEL = os.getenv("ARK_EMBED_MODEL", "doubao-embedding-vision-251215")

# ---------- 自进化 ----------
# True：审核通过后自动重新归纳总纲（默认，演示效果最好）
AUTO_REFRESH_SUMMARY = os.getenv("AUTO_REFRESH_SUMMARY", "true").lower() != "false"

# ---------- 公网体验模式 ----------
# 把 demo 挂到公网给别人点开体验时打开，防止 API 余额被刷光。
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
# 单个 IP 每天最多几次对话（0 = 不限）
DEMO_PER_IP_DAILY = int(os.getenv("DEMO_PER_IP_DAILY", "30"))
# 全站每天最多几次对话（0 = 不限）
DEMO_GLOBAL_DAILY = int(os.getenv("DEMO_GLOBAL_DAILY", "800"))

# 需求槽位定义（顺序即追问顺序）
# 注意：装修阶段用 stage_reno，别和 leads.stage（客户阶段 inquiry/qualified）混淆
REQUIRED_SLOTS = [
    ("scenario", "想装哪一块", "全屋智能 / 只做灯光 / 只做安防 / 影音 / 窗帘"),
    ("area", "房子多大", "建筑面积，如 120 平"),
    ("layout", "户型", "如 三室两厅"),
    ("stage_reno", "装修到哪一步", "毛坯 / 硬装中 / 已入住"),
    ("budget", "预算大概多少", "如 3 万左右"),
    ("community", "在哪个小区", "用于查同小区案例"),
]
SLOT_KEYS = [k for k, _, _ in REQUIRED_SLOTS]

# 报价红线：这些词出现时，说明模型在给"精确总价"，需要拦截
PRICE_BANNED_PATTERNS = [
    r"总价\s*[:：]?\s*\d",
    r"一共\s*\d+\s*[万千]",
    r"总共\s*\d+\s*[万千]",
    r"打包价\s*[:：]?\s*\d",
]

# 合规红线（触发即拦截并改写）
COMPLIANCE_BANNED = [
    "绝对", "百分百", "100%", "保证", "包过", "零风险", "最便宜", "全网最低",
    "加微信", "加我微信", "微信转账", "私下交易", "刷单", "好评返现",
]
