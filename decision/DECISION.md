太好了，这一步**非常对路**。下面我直接给你一个**可落地的 `/decision` CLI 工具设计**，专门为你这种：

* 多模型（Claude / Codex / Gemini）
* 多 Agent 角色
* 用来**降认知压力而不是写代码**

而设计。

我会给你：

1. **CLI 使用体验（你跑起来是什么样）**
2. **目录 & 数据结构**
3. **Agent 调度与角色映射**
4. **Prompt 模板（关键）**
5. **裁决与停止规则**
6. **第一版 MVP 实现建议（1–2 天可完成）**

---

## 一、你最终用起来应该是这样（目标体验）

### 1️⃣ 创建一个决策议题

```bash
aq decision new options_lifecycle_v1
```

交互式输入：

```
Decision title: 是否现在实现完整 Options Lifecycle
Current option (A):
> 自动 expiration / assignment / roll

Alternative option (B):
> 只做监控 + alert，人工处理

Constraints:
> 单人维护，6 个月内实盘，不能影响稳定性
```

生成：

```
decisions/options_lifecycle_v1/
├── decision.yaml
└── council/
```

---

### 2️⃣ 召集议会（并行问多个 Agent）

```bash
aq decision council options_lifecycle_v1
```

CLI 输出：

```
Invoking Decision Council:
- Skeptic     (Claude)
- Minimalist  (Gemini)
- Operator    (Codex)
- Quant       (Claude)
- Historian  (Gemini)

Running agents... (parallel)
```

结果：

```
✔ council/skeptic.md
✔ council/minimalist.md
✔ council/operator.md
✔ council/quant.md
✔ council/historian.md
```

---

### 3️⃣ 你裁决（这是关键）

```bash
aq decision decide options_lifecycle_v1
```

编辑器自动打开一个模板，让你**只填判断，不写长文**。

---

## 二、目录结构（非常简单，但极其重要）

```text
decisions/
└── options_lifecycle_v1/
    ├── decision.yaml          # 决策输入（不可变）
    ├── council/
    │   ├── skeptic.md
    │   ├── minimalist.md
    │   ├── operator.md
    │   ├── quant.md
    │   └── historian.md
    └── verdict.md             # 你的裁决（唯一权威）
```

> ⚠️ 原则：
> **Agent 只能写 council/**
> **人类只能写 verdict.md**

---

## 三、decision.yaml（议会的“宪法”）

```yaml
id: options_lifecycle_v1
title: 是否现在实现完整 Options Lifecycle

options:
  A: 自动 expiration / assignment / roll
  B: 只监控 + alert，人工处理

constraints:
  - 单人维护
  - 6 个月内实盘
  - 稳定性优先于功能完整

stop_rule:
  max_agents: 5
  stop_when:
    - failure_modes_repeat: true
    - no_new_risk: true
```

---

## 四、Agent 角色映射（你现在的工具刚好够用）

| 角色         | CLI        | 原因                      |
| ---------- | ---------- | ----------------------- |
| Skeptic    | Claude CLI | 最擅长系统性 failure thinking |
| Quant      | Claude CLI | 统计 & regime 思维          |
| Minimalist | Gemini CLI | 擅长 challenge scope      |
| Historian  | Gemini CLI | 事故 & 类比                 |
| Operator   | Codex CLI  | 工程/运维/实现现实              |

> 这不是“谁更强”，而是**谁更适合这个人格**。

---

## 五、统一 Prompt 模板（最重要的部分）

> ⚠️ 不允许每次临时发挥
> ⚠️ Prompt 是“制度”，不是“灵感”

### `prompts/base_decision.md`

```md
You are a member of a Decision Council.
Your role is fixed and defined below.

You are NOT allowed to:
- Propose a final solution
- Give emotional reassurance
- Say "it depends"

You MUST:
- Enumerate failure modes
- Describe consequences
- Focus on your role’s perspective only
```

---

### 例：`prompts/skeptic.md`

```md
Role: Skeptic (Catastrophic Failure Engineer)

You assume the system WILL fail.

Given the decision context below, answer strictly in this format:

## Top Failure Modes
1.
2.
3.

## Catastrophic Risk
- Trigger:
- Why it's overlooked:
- Worst outcome:

## Early Warning Signals
- Signal 1
- Signal 2
```

> Gemini / Codex / Claude **全部用同一结构**
> 这样你不会被语言质量骗。

---

## 六、Agent 调用方式（非常现实）

### Claude CLI（示例）

```bash
claude \
  --prompt "$(cat prompts/base_decision.md prompts/skeptic.md)" \
  --context decision.yaml \
  --output council/skeptic.md
```

### Gemini CLI / Codex CLI 同理

你只需要一个小 dispatcher（Python / bash 都行）。

---

## 七、verdict.md（真正“降认知压力”的地方）

你不是写 essay，你只填判断。

```md
# Decision Verdict

Chosen Option: B

## Known Risks I Accept
- 延迟自动 assignment 可能在极端情况下需要人工干预
- 人工操作存在失误风险

## Risks I Explicitly Reject
- 自动 lifecycle 在边界条件下误操作真实仓位
- 回测不足情况下引入复杂状态机

## Why This Is Acceptable Now
- 当前阶段稳定性 > 自动化
- 人工可控风险 < 系统性不可控风险

Decision Date: 2026-01-22
Revisit After: 3 months
```

> **一旦写完这个，心理负担会明显下降**
> 因为你已经“看清楚自己在赌什么”。

---

## 八、停止规则（防止你陷入无限征询）

CLI 自动检查：

* council/*.md 中 failure mode 是否重复
* 是否 2 个以上 Agent 指向同一 catastrophic risk

满足任一条件：

```
⚠️ Council saturation reached.
Further agent queries unlikely to add new information.
Recommend proceeding to verdict.
```

---

## 九、MVP 实现建议（非常现实）

**Day 1**

* decision.yaml
* prompts/
* 手动调用 CLI

**Day 2**

* `aq decision new`
* `aq decision council`
* `aq decision decide`

不需要数据库，不需要 Web，不需要 FastAPI。

---

## 十、一句非常重要的实话（给你定锚）

> **这个工具不是为了“做对决策”，
> 而是为了让你在做错时，
> 也能心里平静地说一句：
> “我当时已经尽力看清风险了。”**

这对长期做系统、做交易的人，**价值极高**。

---

如果你愿意，下一步我可以：

* **直接帮你写一个最小 `aq decision` Python CLI skeleton**
* 或 **拿你 STRATEGY.md 里的一个真实问题，直接帮你跑一轮示例输出**

你选一个，我直接继续。
