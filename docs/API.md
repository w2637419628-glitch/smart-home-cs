# API 参考

> 启动后打开 **http://127.0.0.1:8100/docs** 就是可交互的 Swagger 文档（FastAPI 自动生成），
> 可以直接在页面上发请求。本文是给命令行/脚本用的速查版。

基础地址：`http://127.0.0.1:8100`

---

## 一、对话

### POST `/api/chat`

跑一轮 Agent Loop，返回回复 + 完整执行轨迹。

```bash
curl -s -X POST http://127.0.0.1:8100/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"120平毛坯，想做全屋智能，大概多少钱","session_id":"demo"}'
```

```jsonc
{
  "reply": "价格得看具体做到什么程度，我先跟您确认几件事：您家是几室几厅？",
  "handoff": false,          // 是否转了人工
  "ticket_id": null,         // 转人工时的工单号
  "survey_id": null,         // 约成勘测时的工单号
  "slots_filled": 3,         // 已收集的需求项
  "slots_total": 6,
  "lead": { "scenario": "全屋智能", "area": 120, "stage_reno": "毛坯" },
  "trace": [
    { "step": 1, "type": "llm_call",     "messages": [...], "available_tools": [...6 个] },
    { "step": 1, "type": "llm_response", "decision": "tool_call", "tool_calls": [...] },
    { "step": 1, "type": "think",        "content": "先看店长教过哪些类似的话术" },
    { "step": 1, "type": "tool_call",    "tool": "recall_playbook", "input": {...} },
    { "step": 1, "type": "tool_result",  "tool": "recall_playbook", "output": {...}, "is_error": false },
    { "step": 2, "type": "tool_call",    "tool": "save_requirements", "input": {...} },
    { "step": 3, "type": "final",        "content": "..." }
  ]
}
```

`trace[].type` 的取值：

| type | 含义 |
|---|---|
| `llm_call` | 这一步喂给模型的完整上下文 |
| `llm_response` | 模型的原始决策 |
| `think` | 模型的思考 |
| `tool_call` / `tool_result` | 工具调用与观测 |
| `final` | 收尾 |
| `compliance_blocked` | 触发合规拦截，附原回复与原因 |
| `hallucination_blocked` | 未学过却给了硬承诺，被拦截 |
| `uncovered_answered` | 未命中样本，按铁律授权的泛化作答 |
| `ticket_autocreated` | 模型口头转人工但没建单，系统补建 |
| `llm_error` | 模型服务不可用，已降级为友好提示 |

**体验模式**下超额返回 `429`：

```json
{ "detail": "您今天的体验次数（30 次）已经用完了。" }
```

### POST `/api/session/reset`

清空这个会话的**对话历史 + 客户档案**。

```bash
curl -s -X POST 'http://127.0.0.1:8100/api/session/reset?session_id=demo'
```

### GET `/api/lead/{session_id}`

查客户档案与缺失槽位。

```bash
curl -s http://127.0.0.1:8100/api/lead/demo
# {"lead":{...},"filled":3,"total":6,"missing":["layout","budget","community"]}
```

---

## 二、教学与审核

### POST `/api/teach`

店长教一条示范。**进待审，不立即生效**。

```bash
curl -s -X POST http://127.0.0.1:8100/api/teach \
  -H 'Content-Type: application/json' \
  -d '{"question":"你们能做弧形柜吗？",
       "answer":"弧形柜可以做，属于异形定制，要先出图确认弧度。",
       "note":"异形工艺要如实说清加价和工期，不要一口答应。"}'
# {"ok":true,"sample_id":21,"status":"pending"}
```

### GET `/api/playbook`

```bash
curl -s 'http://127.0.0.1:8100/api/playbook'                    # 全部
curl -s 'http://127.0.0.1:8100/api/playbook?status=pending'     # 待审
curl -s 'http://127.0.0.1:8100/api/playbook?source=ticket'      # 工单补充的
```

### POST `/api/playbook/{id}/approve`

**这是自进化的关键动作**：入库 + 自动归纳总纲 + 关闭重复工单。

```bash
curl -s -X POST http://127.0.0.1:8100/api/playbook/21/approve
```

```jsonc
{
  "ok": true,
  "summary_changed": true,
  "added": ["13. 客户问异形/定制工艺（如弧形柜等）能否做时……"],
  "tickets_closed": 3,
  "summary": "1. 价格类问题一律不先报数字……"
}
```

### POST `/api/playbook/{id}/reject` · DELETE `/api/playbook/{id}`

驳回或删除样本。

---

## 三、套路总纲

### GET `/api/summary`

返回已保存的总纲 + 上一版 diff。**首次访问且为空时，会自动归纳一次（会调模型）。**

```bash
curl -s http://127.0.0.1:8100/api/summary
# {"summary":"1. ...","prev":"...","added":[...],"removed":[...]}
```

### PUT `/api/summary`

店长手动改写总纲（重归纳时作为基底保留）。

```bash
curl -s -X PUT http://127.0.0.1:8100/api/summary \
  -H 'Content-Type: application/json' \
  -d '{"text":"1. 绝不报总价\n2. 报价前先问六件事"}'
```

### POST `/api/summary/refresh`

重新归纳。两个可选参数：

| 参数 | 作用 |
|---|---|
| （默认） | 增量归纳，保留人工改写 |
| `?force_all=true` | 全部样本重喂，仍以现有总纲为基底 |
| `?rebuild=true` | **丢掉现有总纲**，纯从当前样本重建 |

```bash
curl -s -X POST 'http://127.0.0.1:8100/api/summary/refresh?rebuild=true'
```

> `rebuild` 用在"样本删了但总纲还留着它的原则"这种不一致场景。

---

## 四、工单

### GET `/api/tickets`

```bash
curl -s 'http://127.0.0.1:8100/api/tickets?status=open'
```

每条带一个 `hit_score`：用**当前样本库**去检索这条工单的问题。
≥ 0.4 说明"现在应该能答上来了"，可以考虑关闭。

```jsonc
{ "id": 35, "kind": "ticket", "status": "open", "dupe_count": 2,
  "question": "你们只做家居这一块吗", "hit_score": 0.067 }
```

### POST `/api/tickets/{id}/teach`

针对工单补答案 → 进待审。

```bash
curl -s -X POST http://127.0.0.1:8100/api/tickets/35/teach \
  -H 'Content-Type: application/json' \
  -d '{"answer":"我们也做办公空间和民宿。","note":"超出范围但能做，先肯定再引导。"}'
# {"ok":true,"sample_id":22,"status":"pending","closed_similar":1}
```

### POST `/api/tickets/{id}/close`

直接关闭，不教学。

---

## 五、配置与观测

### GET / PUT `/api/settings/directive`

业务铁律（最高优先级，后台可改）。

```bash
curl -s http://127.0.0.1:8100/api/settings/directive
curl -s -X PUT http://127.0.0.1:8100/api/settings/directive \
  -H 'Content-Type: application/json' \
  -d '{"text":"【铁律】1. 绝不报总价\n2. ..."}'
```

### GET `/api/settings/system-prompt`

**四层拼装后的完整提示词原文**。用来核对"到底教进去了什么"。

```bash
curl -s http://127.0.0.1:8100/api/settings/system-prompt | python -m json.tool
```

### GET `/api/metrics`

```jsonc
{
  "samples_approved": 21, "samples_pending": 0,
  "total_chats": 80, "handoff_count": 26, "handoff_rate": 0.325,
  "hit_count": 38, "hit_rate": 0.475,
  "avg_slots_filled": 2.71,
  "survey_booked": 2, "tickets_open": 1
}
```

### GET `/api/status`

```jsonc
{
  "app": "会进化的智能家居客服",
  "provider": "openai:deepseek-chat",     // 或 mock(离线桩)
  "auto_refresh_summary": true,
  "quota": { "demo_mode": true, "global_used": 3, "global_limit": 800,
             "per_ip_limit": 30, "distinct_ips": 2 },
  "slots": [{"key":"scenario","label":"想装哪一块"}, ...]
}
```

---

## 六、5 分钟跑通一次自进化（纯 curl）

```bash
B=http://127.0.0.1:8100
H='Content-Type: application/json'

# 1) 问一个没学过的 → 转人工
curl -s -X POST $B/api/chat -H "$H" \
  -d '{"message":"你们能做弧形柜吗？","session_id":"t1"}'
# → handoff=true, ticket_id=12

# 2) 店长补答案 → 进待审
curl -s -X POST $B/api/tickets/12/teach -H "$H" \
  -d '{"answer":"弧形柜可以做，属于异形定制，要先出图。","note":"异形要讲清加价和工期。"}'
# → sample_id=21, status=pending

# 3) 待审时再问一次 → 仍然转人工（闸门生效）
curl -s -X POST $B/api/chat -H "$H" \
  -d '{"message":"你们能做弧形柜吗？","session_id":"t2"}'

# 4) 审核通过 → 自动归纳
curl -s -X POST $B/api/playbook/21/approve

# 5) 看总纲变了什么
curl -s $B/api/summary

# 6) 再问一次 → 直接答对
curl -s -X POST $B/api/chat -H "$H" \
  -d '{"message":"你们能做弧形柜吗？","session_id":"t3"}'
```

---

## 七、错误码

| 状态码 | 含义 |
|---|---|
| 200 | 正常 |
| 429 | 体验模式超额（`detail` 里有提示语） |
| 404 | 工单/样本不存在 |
| 500 | 通常已由兜底吃掉；真出现看 `journalctl -u smart-home-cs -f` |
