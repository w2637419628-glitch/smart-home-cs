# 会进化的智能家居客服

> **Agent Loop + 示范学习 + 审核固化**：一套不用训练模型、越用越准的销售 Agent 后端。

店长教一句「这种情况该怎么答、为什么这么答」，系统把它沉淀成**可检索的话术**和**可注入的套路总纲**，下一轮对话立刻生效。
答不上来的问题自动转人工 → 店长补答案 → 审核通过 → 固化进提示词 → 下次答对。

> 本项目**只提供 HTTP API**，不含前端界面。启动后打开 `/docs` 就是 FastAPI 自动生成的交互式文档，可以直接在浏览器里发请求。
>
> 线上体验站另有一套简易界面，**不在本仓库内**——这里聚焦后端实现与设计。

---

## 一、它解决什么问题

普通客服机器人是「有问必答」：客户问多少钱，它就报多少钱。
真实销售不是这样——问价要先问需求，嫌贵要给替代路径，没把握的事不能吹。

这套系统要验证的是三件事：

| 要验证的 | 怎么验证 |
|---|---|
| 模型能不能**自己决定**调什么工具 | 一次对话里串起 `查样本 → 记需求 → 查套餐 → 查案例`，顺序不由代码写死 |
| 模型能不能**拒绝回答** | 没学过 → 转人工 + 建工单，绝不编 |
| 经验能不能**自动沉淀** | 教一句 → 审核 → 总纲自动重写 → 下一轮生效 |

---

## 二、核心能力

| 能力 | 实现 |
|---|---|
| **Agent Loop** | 一个 `while` 循环，模型自主选工具 / 决定收尾；5 重护栏防死循环 |
| **需求挖掘** | `save_requirements` 工具把"问齐 6 项需求"变成**可观测动作** |
| **示范学习** | 教学/工单 → 待审 → 通过 → LLM 归纳总纲 → 注入 prompt |
| **可控进化** | 人工改写优先（状态合并），AI 不会覆盖店长的修订 |
| **报价红线** | 套餐表里**没有 `total_price` 字段**，物理上报不出总价 |
| **承诺分级** | 泛化的"能做"放行，硬承诺（工期/保证/绝对）拦截转人工 |
| **三道兜底** | 合规拦截 / 口头转人工自动补单 / 未覆盖问题留痕 |
| **可观测** | 每轮完整 trace：模型看到什么、决定什么、工具返回什么 |

---

## 三、架构速览

```
接口层  FastAPI（19 个路由）
   ↓
编排层  chat_service：每轮重建提示词 → 驱动 Loop → 合规兜底 → 记账
   ↓
智能层  AgentLoop：模型决策 → 调工具 → 观察 → 再决策 → 收尾
        ↑ 6 个工具          ↑ 4 重护栏
   ↓
知识层  样本库（top-k 检索）+ 套路总纲（常驻注入）
   ↓
模型层  LLMProvider 抽象：OpenAI 兼容（DeepSeek/豆包）| 离线桩（mock）
```

**关键：智能层只依赖抽象。** 换模型只需实现一个 `chat()`，加能力只需登记一个 `Tool`。

详细设计见 **[docs/架构设计.md](docs/架构设计.md)**。

---

## 四、快速开始

### 1. 装依赖

```bash
pip install -r requirements.txt
# 国内慢就用镜像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 2. 配置模型（可选）

```bash
cp .env.example .env
```

```ini
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-你的key
LLM_MODEL=deepseek-chat
```

> **不配也能跑**：没有 `.env` 时自动用离线规则桩（mock），断网也能跑完整闭环，只是话术偏模板。

### 3. 启动

```bash
python start.py     # 自动打开 /docs
# 或
python run.py       # 然后手动开 http://127.0.0.1:8100/docs
```

首次启动自动建库，并灌入 **20 条种子话术 + 5 个套餐 + 8 个完工案例**。

---

## 五、30 秒看效果

```bash
B=http://127.0.0.1:8100

# 问价格 —— 它不会报价，而是反问需求
curl -s -X POST $B/api/chat -H 'Content-Type: application/json' \
  -d '{"message":"120平毛坯，全屋智能大概多少钱","session_id":"demo"}'
```

返回里能看到完整的推理链：

```jsonc
{
  "reply": "价格得看具体做到什么程度，我先跟您确认几件事：您家是几室几厅？",
  "trace": [
    {"type":"llm_call",   "available_tools":["recall_playbook","save_requirements", ...]},
    {"type":"tool_call",  "tool":"recall_playbook"},
    {"type":"tool_result","tool":"recall_playbook","output":{"count":4,"top_score":0.169}},
    {"type":"tool_call",  "tool":"save_requirements","input":{"slots":{"scenario":"全屋智能","area":120}}},
    {"type":"final",      "content":"..."}
  ]
}
```

**完整 API 见 [docs/API.md](docs/API.md)**，含"5 分钟跑通一次自进化"的纯 curl 脚本。

---

## 六、四个关键设计

### 1. 决策权交给模型，不写意图分类

Loop 只依赖 `LLMProvider.chat()` 和 `Tool` 两个抽象。
新增业务场景 = 加一个工具，**控制流一行不改**。

### 2. 危险能力在数据结构层面就不存在

```python
# package_search 的返回值里根本没有总价字段
{"price_min": 25000, "price_max": 38000, "includes": "...", "excludes": "..."}
```

报价红线不靠"提示词自觉"——模型想报也拿不到数。

### 3. 检索 + 归纳，两条路同时走

| 路径 | 内容 | 解决什么 |
|---|---|---|
| 检索（按需） | top-k 样本 | 库变大不会撑爆上下文 |
| 注入（常驻） | 套路总纲 | 覆盖没见过的问法 |

只用检索 → 换问法就废；只用总纲 → 具体话术丢失。

### 4. 可控进化 > 自动进化

重新归纳总纲时，把店长手改的版本作为基底传进去，冲突以人工为准。
**没有这一步，店长改三次被覆盖两次，就再也不改了。**

---

## 七、目录结构

```
smart-home-cs/
├── run.py                      启动入口
├── start.py                    带环境检查的启动器（自动开 /docs）
├── app/
│   ├── config.py               槽位 / 铁律 / 合规词 / 检索阈值
│   ├── db.py                   7 张表
│   ├── main.py                 19 个 API 路由
│   ├── agent/
│   │   ├── loop.py             ★ Agent Loop 引擎
│   │   └── tools/              6 个工具
│   ├── knowledge/embedder.py   向量 + IDF 词法双后端
│   ├── llm/                    模型抽象（OpenAI 兼容 | mock）
│   ├── services/
│   │   ├── coach_service.py    ★ 归纳总纲 / 自动固化 / 四层提示词
│   │   ├── playbook_service.py  样本库（待审 + top-k）
│   │   ├── chat_service.py      对话 / 合规兜底 / 转人工兜底
│   │   ├── lead_service.py      客户档案（6 个需求槽位）
│   │   ├── review_service.py    工单 + 看板
│   │   └── settings_service.py  铁律 / 总纲持久化
│   └── data/                   套餐 / 案例 / 20 条种子话术（演示数据）
├── docs/
│   ├── 架构设计.md               ★ 为什么这么设计
│   ├── API.md                  接口参考 + curl 示例
│   ├── 需求清单.md              做什么 / 不做什么 / 验收标准
│   └── 演示脚本.md              逐幕演示流程
└── deploy/                     Docker / systemd / 部署指南
```

---

## 八、技术栈

- **Python 3.11+** / **FastAPI** / **Pydantic**
- **SQLite**（单文件，无外部依赖）
- **OpenAI 兼容接口**（DeepSeek / 火山豆包，换 base_url 即可）
- **零前端依赖**（用 FastAPI 自带的 `/docs`）

---

## 九、测试

```bash
python _test_guard.py    # Agent Loop 护栏：模型卡死时会不会收敛
python _dev_test.py      # 七幕闭环（直连服务层，用独立测试库）
python _smoke_test.py    # 七幕闭环（走 HTTP，需先启动服务）
```

三套都要看到 `ALL PASSED` / `护栏生效`。

> `_dev_test.py` / `_test_guard.py` 用 `DSH_DB_PATH` 指向临时库，不会污染演示数据。
> `_smoke_test.py` 跑在演示库上，收尾会重建总纲。

---

## 十、已知限制（诚实记录）

| # | 限制 | 说明 |
|---|---|---|
| 1 | **检索弱** | 默认是字符 bigram + IDF 的**词法匹配**，不是 embedding。实测"保修几年"命中分 0.000（库里有售后话术却找不到）。接 `ARK_API_KEY` 可切向量后端，但更适合直接换 `bge-small-zh` |
| 2 | **语料是模拟数据** | 套餐、案例、话术全部是为了演示编的，不是真实业务数据 |
| 3 | **单机** | SQLite + 进程内会话，重启丢上下文，不支持多 worker |
| 4 | **无鉴权** | 所有接口公开，前后台不分离 |
| 5 | **无流式** | 真实模型单轮 2–4 秒 |
| 6 | **只处理文本** | 不支持图片/语音 |
| 7 | **无结果归因** | 只有技术指标（转人工率/命中率），没有留资率/成交率 |

**路线图**（按价值排序）：

1. 换真 embedding（`bge-small-zh`）+ 文档分块 + 混合检索
2. 结果信号归因：留资 → 到店 → 成交，按会话回溯
3. 话术按销售阶段分域检索
4. 流式输出

---

## 十一、文档

| 文档 | 内容 |
|---|---|
| [docs/架构设计.md](docs/架构设计.md) | 分层、Loop 四重护栏、自进化四步、提示词四层、检索局限、关键取舍 |
| [docs/API.md](docs/API.md) | 19 个接口 + curl 示例 + 5 分钟自进化脚本 |
| [docs/需求清单.md](docs/需求清单.md) | 定位、做什么/不做什么、5 条铁律、验收标准、v2 规划 |
| [docs/演示脚本.md](docs/演示脚本.md) | 逐幕演示流程与翻车预案 |
| [deploy/部署指南.md](deploy/部署指南.md) | 服务器部署（Docker / systemd / nginx） |

---

## 十二、License

MIT
