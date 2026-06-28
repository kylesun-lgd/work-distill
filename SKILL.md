---
name: work-distill
description: 工作内容沉淀 skill。当用户完成一段工作、想要记录/沉淀/总结工作进展、产出、决策、待办时使用。也用于"沉淀一下"、"记录进度"、"归档这次工作"、"更新项目状态"。把当前 agent 会话产出写入本地运行环境：项目 MD（agent 的活说明书，下次执行先读它了解现状）+ 网页驾驶舱（可浏览）。支持多 agent 多对话通过项目 slug 统一聚合。
---

# 工作沉淀（work-distill）

把"本次会话做了什么"提炼成一条结构化记录，写入本地运行环境：**项目 MD**（每个项目的活说明书 + agent 提示词）+ **网页驾驶舱**（可浏览）。纯本地运行，所有数据存一个目录。

## 何时触发

用户说"沉淀一下"、"记录进度"、"归档这次工作"、"更新项目状态"，或在完成一个工作单元后主动沉淀。手动触发为主。

## 执行流程（重要）

### 第 0 步：确认项目身份（先看上下文，再决定是否问用户）

**沉淀前，先判断这个对话里之前是否用过本 skill：**

**情况 A：上下文里有沉淀记录**（本对话之前沉淀过，能看到 sediment.py 的输出或项目 MD 内容）
→ 已知 slug，直接用，**不用再问用户**。继续第 1 步读项目 MD。

**情况 B：上下文里没有沉淀记录**（本对话第一次触发 skill，或上下文被压缩过）
→ 问用户："这个项目是第一次用这个 skill 吗？"
   - **是第一次** → 让用户给项目命名，商定一个 slug（首次显式指定，之后所有 agent 都用这个）。然后继续第 1 步（新项目无 MD，会自动创建）。
   - **不是第一次** → 跑 `--list-projects` 查已有项目，让用户确认当前工作对应哪个：
     ```bash
     python3 ~/.agents/skills/work-distill/scripts/sediment.py --list-projects
     ```
     用户确认后，用该项目的 **slug**（必须一致）和**显示名**（沿用已有，不自己编）。

> 为什么先看上下文：如果本对话已经沉淀过，agent 应该记得 slug，不必反复问用户。只有"第一次"或"压缩后丢失"才需要问。这平衡了顺滑与准确。

#### 上下文压缩后的恢复（重要）

长对话可能被平台压缩，导致"用过 skill"的信息丢失。恢复方法——**不依赖对话历史，靠磁盘锚点**：

```bash
# 1. 读 current.txt 知道最近在处理哪个项目
python3 ~/.agents/skills/work-distill/scripts/sediment.py --current
# 输出：最近沉淀的 slug + 显示名 + 项目 MD 路径

# 2. 读该项目 MD 恢复完整上下文
cat <运行环境>/projects/<slug>.md
```

- `current.txt` 是 sediment.py 每次沉淀后自动写的，记录最近项目 slug——它是压缩后的恢复锚点。
- 项目 MD 的「概况+焦点」是最新快照，读完就恢复项目现状认知。
- **压缩后不要猜项目身份**，先 `--current` 再读 MD，比从压缩摘要里推断可靠。

### 第 1 步：先读项目 MD（如果有）

**确认项目身份后，读该项目的 MD 文件**，了解项目现状再沉淀。这是本 skill 的核心——MD 是"活说明书"，让你（不同 agent）能接上上下文：

```bash
cat <运行环境>/projects/<slug>.md
```

- MD 顶部「项目概况 + 当前焦点」是最新快照（每次沉淀会重写），读懂它你就知道项目到哪了、下一步做什么。
- 如果是新项目（MD 不存在），跳过这一步，本次沉淀会创建它。
- **读项目 MD 不算"读项目文件"违规**——读的是沉淀 skill 自己维护的状态文件，不是项目源码。控制 token 的约束针对的是项目源码/历史文档，项目 MD 是必读的。

### 第 2 步：回顾本次会话 + 项目现状，提炼字段

结合**当前会话内容**和**第 1 步读到的项目现状**，提炼：

| 字段 | 必填 | 说明 |
|---|---|---|
| `project` | ✅ | 项目显示名（人看的，可含空格大小写） |
| `project-slug` | 推荐 | 项目稳定标识（跨 agent 统一聚合用）。同一项目无论在 ZCode/Codex/Claude Code 里，**slug 必须一致**。不填则由显示名生成 |
| `type` | ✅ | `progress`（进展）/ `decision`（决策）/ `knowledge`（知识）/ `archive`（归档到创意仓库）/ `reactivate`（从创意仓库重新激活） |
| `summary` | ✅ | 一句话摘要，≤40 字 |
| `agent` | ✅ | 你的标识，如 `zcode/glm-5.2`、`claude/sonnet`、`codex`（区分来源） |
| `status` | 默认 in-progress | `in-progress` / `done` / `blocked` / `archived`（归档时用 archived） |
| `next` | 推荐 | 下一步待办数组，**每项是对象**：`{"t":"待办内容","p":"高/中/低","prog":"50%"}`。`p` 是优先级，`prog` 是当前进度百分比 |
| `artifacts` | 可选 | 产出文件**绝对路径**数组 `["/Users/.../docs/spec.md"]`。网页端"在访达中显示"靠绝对路径定位，相对路径会找不到文件 |
| `goal` | 可选 | 项目目标（首次沉淀某项目时写入，后续默认不覆盖；要改用 `--update-meta`） |
| `stage` | 可选 | 项目当前阶段（首次写入，后续默认不覆盖；要改用 `--update-meta`） |
| 正文 | 推荐 | 经 stdin 传入：本次做了什么、关键决策、沉淀的知识。会写入项目 MD 概况区，作为下次执行的上下文 |

**关于 next 的优先级和进度**：尽量为每条 next 标注 `p`（优先级）和 `prog`（进度，0% 起）。这是用户最关心的"下一步该做什么"。判断不了优先级可省略 `p`，但鼓励尽量给。

### 第 3 步：调用 sediment.py

```bash
echo "正文内容：本次完成了设计稿，采用本地运行环境模型……" | python3 ~/.agents/skills/work-distill/scripts/sediment.py \
  --project "内容沉淀skill" \
  --project-slug "content-distill" \
  --type progress \
  --summary "完成沉淀 Skill 设计稿" \
  --agent "zcode/glm-5.2" \
  --status in-progress \
  --next '[{"t":"用户审批设计方案","p":"高","prog":"50%"},{"t":"落地脚本","p":"中","prog":"10%"}]' \
  --artifacts '["/Users/.../docs/spec.md"]' \
  --goal "做一个工作沉淀 skill" \
  --stage "设计中"
```

**`--next` 和 `--artifacts` 必须是合法 JSON 字符串**（单引号包裹，内部双引号）。`--next` 每项必须是含 `t` 的对象。`--artifacts` 必须用**绝对路径**，否则网页端"在访达中显示"无法定位文件。

### 第 4 步：报告结果

转告用户：✅ 已沉淀到哪个项目 MD + 网页查看地址。

## 首次使用：初始化（一次性，跨工具共享）

```bash
python3 ~/.agents/skills/work-distill/scripts/setup.py init
```

交互式确认（带默认值，回车即用）：
- 运行环境根目录（默认 `~/Documents/Zcode/work-distill`）
- 本地服务端口（默认 7788）
- 默认 agent 标识（如 `zcode/glm-5.2`）

setup 会建运行环境目录结构（`data/entries`、`data/index`、`projects`）、复制网页模板、写本工具配置。也支持参数式：`setup.py init --env ~/path --port 7788`。

**跨工具共享**：运行环境路径固定在默认位置（或写入全局标记 `~/.work-distill-env`）。你在 Codex 里初始化后，Hermes/ZCode 等其它工具装的同名 skill 会**自动发现**同一个运行环境，无需各自初始化——因为环境路径不绑死在某个 skill 目录里。任一工具装的 skill 都能读能写同一份项目 MD 和数据。

## 修改配置

```bash
python3 ~/.agents/skills/work-distill/scripts/setup.py config        # 交互式逐项改
python3 ~/.agents/skills/work-distill/scripts/setup.py config --env <新路径>  # 直接改某项
```

## 数据去哪了（纯本地）

所有数据在运行环境目录（默认 `~/Documents/Zcode/work-distill`）：

```
work-distill/
├── index.html                # 网页驾驶舱（serve.py 起服务后浏览器访问）
├── data/
│   ├── entries/YYYY-MM/      # 每条沉淀的正文分片
│   └── index/YYYY-MM.jsonl   # 按月分片索引（网页懒加载）
└── projects/<slug>.md        # 项目 MD（agent 的活说明书 + 提示词，下次执行先读）
```

- **项目 MD**（`projects/<slug>.md`）：概况+焦点区每次重写为最新快照，历史区追加保留全部。**这是 agent 接续上下文的关键文件，执行沉淀前必读。**
- **网页数据**：entries 分片 + 按月索引，网页动态 fetch 加载。
- 所有数据存本地一个目录，断网也能用。

## 项目 MD 的结构（你的活说明书）

```markdown
# 内容沉淀skill
<!-- slug: content-distill | agent: zcode/glm-5.2 | ts: ... -->
<!-- goal: ... | stage: ... -->

> agent 执行沉淀前先读本文件，了解项目现状再更新。

## 项目概况          ← 每次重写：目标/阶段/最新动态（你传的正文）
## 当前焦点          ← 每次重写：下一步待办（优先级+进度）
## 更新历史          ← 追加：所有沉淀的时间线
```

概况和焦点是"最新快照"（读懂就知道项目现状），历史是"完整演变"。你执行沉淀前读概况+焦点即可，历史可选读。

## 查看网页

```bash
python3 ~/.agents/skills/work-distill/scripts/serve.py start    # 后台启动 + 打开浏览器
python3 ~/.agents/skills/work-distill/scripts/serve.py stop     # 停止
python3 ~/.agents/skills/work-distill/scripts/serve.py status   # 状态
```

默认 http://localhost:7788 。网页每 30 秒自动刷新，新沉淀秒级可见。

## 多 agent / 多对话如何统一

同一项目可能在 ZCode、Codex、Claude Code、Hermes 等不同工具里被不同 agent 处理。统一性靠四点：

1. **每次沉淀先确认项目身份**：问用户当前工作属于哪个项目；不确定时跑 `sediment.py --list-projects` 查已有项目，用一致的 slug。**不要自己猜 slug**——猜错会导致项目分裂。
2. **`--project-slug` 是跨 agent 的聚合键**。同一项目无论在哪个工具，slug 必须一致。显示名**沿用已有项目列表里的**（不要自己编），保证跨 agent 一致。
3. **`goal` / `stage` 首次写后不覆盖**（要改用 `--update-meta`）。
4. **`next` 写入时自动去重**（同项目 30 天内相同文本不重复加）。

## 项目状态判定（重要：按项目，不按条目）

状态（进行中 / 已完成 / 阻塞 / 创意仓库）是**项目级**的，不是单条沉淀级别的。

- **项目整体状态 = 该项目最近一条沉淀（非归档/激活类型）的 `status`。** 最后一次沉淀标 in-progress，项目就是进行中；标 done 就是已完成；标 blocked 就是阻塞。
- **侧栏状态计数按项目算**：进行中 N 个项目、已完成 N 个项目，而非 N 条沉淀。
- **状态筛选按项目列出**：点"进行中"显示所有进行中的项目卡片，不是条目列表。
- **沉淀时务必准确标注 `--status`**：它决定项目整体状态。若项目实际还在做，最后一条别标 done；卡住了标 blocked。
- 归档态例外：靠 archive/reactivate 记录判定（最近是 archive 即归档，进创意仓库）。

## 阻塞是怎么判断的

1. **手动声明**：沉淀时传 `--status blocked`（项目整体变阻塞）。
2. **超期推断**（网页自动，不改数据）：某条 `next` 从首次出现超 **15 天**且未被新沉淀提到，网页标「⏰疑似阻塞」。

## 归档与重新激活（创意仓库）

**归档**（整项目）：`--type archive --status archived`，或用户说"把 XX 归档/收进创意仓库"。
**重新激活**：`--type reactivate --status in-progress`，或用户说"重新启动 XX"。
归档后项目在网页进入「创意仓库」（状态筛选项，与进行中/已完成/阻塞平级），保留完整历史，可随时重新激活。

## 网页驾驶舱的设计是固定的（重要）

`templates/index.html` 是**成品网页模板**，设计已经定型。执行本 skill 时：

- **不要重写、重新设计、改动 index.html 的样式或结构。** 它是 setup.py 原样复制到运行环境的，sediment.py 只写数据（entries 分片 + 索引），不碰网页本身。
- 网页的布局、配色、组件（侧栏/统计条/待办驾驶舱/项目卡片/详情页 6 板块/产出资料菜单）都是确定的，换任何模型执行本 skill 都应得到同样的网页。
- 项目卡片规范：显示项目名 + 状态 chip + **项目简介**（最近一条沉淀摘要）+ 右下角"待办事项：N"（明确文字标签，非纯数字）。
- 详情页规范：标题 + 项目状态 chip + 目标/阶段 + 「目标与当前焦点」（每项带优先级 chip + 进度条）+「风险与阻塞」+「关键决策记录」+「产出资料」+「附录·更新时间轴」（近 5 条，可展开）。
- 只有用户明确要求改网页设计时才动 index.html，且改完要同步更新本节描述。

## 不要做的事

- **不要读项目源码/历史文档**来补全信息——会费 token 且无必要。项目现状从「项目 MD」读取（这是允许且推荐的），或问用户。
- **不要重写或改动 index.html 网页模板**——它是成品，设计已定型。sediment.py 只写数据。
- 不要把状态理解成"条目级"——状态是**项目级**的，由最近一条沉淀决定。
- 不要在工作未完成时擅自沉淀（除非用户要求）。
- 不要把 `--next` 写成字符串数组（旧格式），必须是对象数组 `[{t,p,prog}]`。
- 不要伪造 `prog`（进度）。基于实际进展给合理估计；不确定就给 `0%`。
- 不要修改 `config.json` 里的路径（除非用户要求改运行环境位置）。
