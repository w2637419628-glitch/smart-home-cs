# AGENTS.md · 项目公约

> **AI 改这个项目的代码前，先读这里。**
> 最后更新：v1.0（已接入 DeepSeek，真实模型验证通过）

---

## 一、这是什么

**智能家居门店的 AI 销售教练**，不是通用客服机器人。

它的价值不在"答得对"，在三点：

1. **敢追问**——信息不足时不推荐方案，先问齐 6 项需求
2. **敢说不会**——没学过就转人工，绝不编
3. **会学**——店长教一句，审核通过后自动固化进系统提示词

如果一次改动让这三点任何一条失效，这个改动就是错的。

---

## 二、不许改的硬约束（改了就是事故）

### H1. `package_search` 的返回里不能出现 `total_price`

报价红线是**数据结构**保证的，不是提示词保证的。只要返回体里带上总价字段，模型迟早会算出来报给客户。

```python
# ✅ 允许
{"price_min": 25000, "price_max": 38000, "includes": "...", "excludes": "..."}

# ❌ 严禁
{"total_price": 32000}
```

### H2. 只有 `status='approved'` 的样本能参与检索

人审闸门（F10）就靠这一行。`recall_topk` / `recall_all_approved` 里必须带 `WHERE status='approved'`。

### H3. 总纲只能通过 `settings_service.set_summary()` 写

它要负责把旧版本存进 `playbook_summary_prev`（用于 diff）。直接 `UPDATE settings` 会让 diff 失效。

### H4. 状态合并不许退化

重新归纳总纲时，`existing`（店长手改的版本）必须作为基底传进模型，并在 `_MERGE_SYSTEM` 里明确"以现有总纲为准"。
**这是"可控进化"的底线**——一旦被 AI 覆盖，店长就再也不敢改总纲了。

### H5. 转人工必须真的建工单

模型嘴上说"让顾问跟您确认"却没调 `handoff` 时，`chat_service` 有兜底自动补建（`_TRANSFER_RE`）。
**别删这段**：没有工单，自进化入口②就断了。

### H6. 重置会话要同时清两样

```python
def reset_session(session_id):
    _SESSIONS.pop(session_id, None)   # 对话历史
    lead_service.reset(session_id)    # 客户档案（否则进度条残留）
```

### H7. 承诺要分级，不能一刀切
店长在铁律第 6 条里授权了「常见、不冷门的工艺可以直接说能做」。所以护栏只拦**硬承诺**，
不拦泛化的"能做"：

| 类型 | 例子 | 处理 |
|---|---|---|
| 泛化能力 | "弧形柜能做"、"悬浮楼梯没问题" | ✅ 放行（铁律授权），trace 记 `uncovered_answered` |
| **硬承诺** | "保证 3 天完工"、"100% 不出问题"、"绝对" | ❌ 拦截 → 改写 + 转人工，trace 记 `hallucination_blocked` |
| 结构安全 | 承重墙、燃气、消防 | ❌ 一律转人工（模型自己判断） |

边界就在 `chat_service._HARD_CLAIM_RE`。动它之前想清楚：
放宽 → 会出现"保证三天装完"这种兑现不了的话；
收紧 → 会把店长授权的正常话术也拦掉，变成"什么都不敢答"。

---

## 三、代码结构约定

### 加一个新工具

1. 在 `app/agent/tools/` 建文件，继承 `Tool`，实现 `name` / `description` / `parameters` / `run()`
2. 在 `app/agent/tools/__init__.py` 的 `build_registry()` 里加一行
3. `run()` 的签名必须带 `**kwargs`（Loop 会注入 `session_id`）
4. 失败时返回 `{"error": "..."}`，**不要抛异常**——Loop 会把 error 当 observation 喂回模型，让它自己纠正

### 加一张表 / 改字段

- 建表语句写在 `app/db.py` 的 `init_db()` 里，用 `CREATE TABLE IF NOT EXISTS`
- 改已有表要给迁移语句（参考原项目的 `ALTER TABLE ... ADD COLUMN` 写法）
- 槽位相关的字段名改动，要同步 `config.REQUIRED_SLOTS`

### 改提示词

| 层 | 位置 | 谁能改 |
|---|---|---|
| ① 技术流程 | `coach_service.BASE_PROMPT` | 只有开发者（代码里） |
| ② 业务铁律 | `settings_service.DEFAULT_DIRECTIVE` 的默认值 / 后台可改 | 店长 |
| ③ 套路总纲 | 归纳生成，店长可改 | 店长 |
| ④ 合规红线 | `coach_service.effective_system_prompt()` 末尾 + `config.COMPLIANCE_BANNED` | 开发者 |

**不要在 ① 里写死业务规则**——规则放 ②，让店长能改。

---

## 四、改完必须跑

```powershell
python _test_guard.py    # 必须看到「护栏生效 ✅」
python _dev_test.py      # 必须看到「ALL PASSED ✅」
python _smoke_test.py    # 需先 python run.py；必须看到「ALL PASSED ✅」
```

三套全绿才算改完。**只跑其中一个不算。**

> 教训：v1 有一次只测了服务层（`_dev_test.py`），漏了 HTTP 路由，结果 `main.py` 里一个 `list + tuple` 让所有对话 500。

> ⚠️ `_smoke_test.py` 跑的是**演示库**，收尾会重建套路总纲。如果店长手工改过总纲，
> 跑测试前先备份（或只跑 `_dev_test.py` + `_test_guard.py`，这两个用独立的临时库）。

---

## 五、已知的坑（踩过的）

| 坑 | 现象 | 解法 |
|---|---|---|
| `stage` vs `stage_reno` | "装修阶段"永远算已填，永不追问 | `leads.stage`=客户阶段，`stage_reno`=装修阶段，别混 |
| 重置不清档案 | 进度条带着上一轮的 6/6 | 见 H6 |
| CSS 缺 `min-height: 0` | 消息一多就划不动 | flex/grid 子项都要加 |
| 模型原地打转 | 同一工具连续调用到步数上限 | `loop.py` 的 `seen` 签名拦截 + `dup_streak` 提前收尾 |
| 口头转人工不建单 | 工单缺失，自进化断链 | 见 H5 |
| 总纲带模型抬头 | 开头多一行"【更新后的套路总纲】" | `coach_service._clean_summary()` |
| 中文引号写进字符串 | 语法错误 `invalid syntax` | 字符串里用「」或中文引号，别用 ASCII 双引号 |
| PowerShell 传中文参数 | 脚本里嵌套引号会被打断 | 用 `.py` 文件跑，别用 `python -c "..."` 拼长串 |

---

## 六、换行业怎么改

保持引擎不动，只换这三处：

```
app/data/packages.py      套餐 / 产品
app/data/cases.py         案例
app/data/seeds.py         种子话术
coach_service.BASE_PROMPT 角色与工作流程
settings_service.DEFAULT_DIRECTIVE  业务铁律
config.REQUIRED_SLOTS     需求槽位
```

`agent/loop.py`、`agent/tools/base.py`、`llm/`、`knowledge/` 都跟行业无关，**不要为了换行业去改它们**。

---

## 七、当前状态

| 项 | 状态 |
|---|---|
| 模型 | `openai:deepseek-chat`（`.env`，mock 可兜底） |
| 测试 | 3 套全绿 |
| 端口 | 8100 |
| 未做 | 结果信号归因、按阶段分域检索、流式、图片消息、A/B —— 详见 `docs/需求清单.md` 第八节 |

---

## 附录：工单去重的三层设计（踩过坑才加的）

同一个问题被问 4 次 → 会建 4 张工单；店长只教了其中 1 张，另外 3 张一直挂在列表里。
现在的处理分三层，**不要简化成"语义相似就自动关闭"**——试过，会误关。

| 层 | 规则 | 安全性 |
|---|---|---|
| ① 建单时 | 问句**归一化后完全相同** → 不新建，`dupe_count + 1` | 安全 |
| ② 教学时 | 关掉与**被教问句一字不差**的其它 open 工单 | 安全 |
| ③ 列表展示 | 给每条工单算一个 `hit_score`（真实检索分），≥ 0.4 标「已学会」，并提供「直接关闭」按钮 | 人确认，最稳 |

**为什么不做自动语义合并**：`燃气管道能不能改` 的检索分是 0.277，却匹配到了「能不能分期？」——
用 0.25 阈值自动关闭会误伤。同理最长公共子串法也会误判（"你们能做弧形柜吗" vs "你们能做全屋智能吗" 共享前缀）。

另一个已修的坑：**模型调 handoff 时会给问题加「客户问：」前缀**，导致教学样本和工单问句不一致、匹配分被稀释。
已在 `handoff.py` 的参数描述里写死"原样复制客户的最后一句话，不要加前缀"。
