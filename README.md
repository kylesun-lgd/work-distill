# work-distill · 工作沉淀 Skill

> 让 AI agent 自动沉淀工作进展，生成**项目活说明书**（agent 可读的上下文）+ **本地网页驾驶舱**（人可浏览）。多 agent 多对话统一聚合，纯本地运行，无外部依赖。

## 解决什么问题

你每天用不同的 agent（ZCode、Codex、Claude Code、Hermes…）处理多个项目。工作开了很多，但：

- ❌ 没法快速了解**目前各项目进展到哪了**
- ❌ 换个 agent/对话，新 agent 不知道**之前做到哪、为什么这么定**
- ❌ 沉淀的资料散落各处，没有统一的地方看

**work-distill** 让 agent 每完成一段工作就自动沉淀一条记录，写入：
1. **项目 MD**（每个项目的"活说明书"）—— agent 下次执行前先读它，秒接上下文
2. **网页驾驶舱**—— 你在浏览器随时查看所有项目的进展、待办、决策、阻塞

## 核心特性

| 特性 | 说明 |
|---|---|
| 📝 **项目 MD = agent 活说明书** | 概况+焦点每次重写为最新快照，历史追加。agent 执行前先读，接上上下文 |
| 🌐 **网页驾驶舱** | 详情页 6 板块：概览/当前焦点/风险阻塞/关键决策/产出资料/更新时间轴，含优先级+进度 |
| 🔗 **多 agent 统一聚合** | 靠 `project-slug` 跨工具归集同一项目；goal/stage 首次写后不覆盖；next 自动去重 |
| 📊 **项目级状态** | 进行中/已完成/阻塞/创意仓库按项目算（非子任务），由最近一条沉淀决定 |
| ⏰ **阻塞两层判断** | 手动 `--status blocked` + 15 天超期自动推断"疑似阻塞" |
| 📦 **创意仓库** | 暂停的项目归档，保留完整历史，可随时重新激活 |
| 🔄 **上下文压缩恢复** | `current.txt` 锚点 + 项目 MD，长对话压缩后也能可靠恢复项目身份 |
| 💾 **纯本地零依赖** | 所有数据存本地一个目录，断网可用，无需任何外部服务 |
| 🎨 **网页设计固化** | index.html 是成品模板，换任何模型执行都得到同样网页 |
| 🪙 **token 友好** | 禁读项目源码，索引按月分片懒加载 |

## 快速开始

### 1. 安装 skill

把本仓库放到 agent 的 skill 目录：

```bash
# ZCode / 通用
cp -r work-distill ~/.agents/skills/

# 或其他工具对应的 skill 目录
```

### 2. 初始化运行环境（一次性）

```bash
python3 ~/.agents/skills/work-distill/scripts/setup.py
```

交互式确认：运行环境路径（默认 `~/Documents/Zcode/work-distill`）、端口、默认 agent。

**跨工具共享**：运行环境路径固定，你在 Codex 初始化后，Hermes/ZCode 等其它工具装的同名 skill 会自动发现同一个环境，无需各自初始化。

### 3. 使用

对你的 agent 说 **"沉淀一下"** / **"记录进度"** / **"归档这次工作"**，agent 会：

```
第 0 步：确认项目身份（先看上下文，没用过才问用户）
第 1 步：读项目 MD，了解现状
第 2 步：提炼本次会话产出（进展/决策/待办/产出）
第 3 步：调用 sediment.py 写入
第 4 步：报告结果
```

### 4. 查看网页驾驶舱

```bash
python3 ~/.agents/skills/work-distill/scripts/serve.py start   # 启动 + 打开浏览器
python3 ~/.agents/skills/work-distill/scripts/serve.py stop    # 停止
```

默认 http://localhost:7788 ，每 30 秒自动刷新。

## 运行环境结构

```
~/Documents/Zcode/work-distill/        # 运行环境（setup.py 创建）
├── index.html                         # 网页驾驶舱（成品模板，勿改）
├── current.txt                        # 最近项目锚点（压缩恢复用）
├── data/
│   ├── entries/YYYY-MM/               # 沉淀正文分片
│   └── index/YYYY-MM.jsonl            # 按月分片索引（网页懒加载）
└── projects/<slug>.md                 # 项目 MD（agent 活说明书 + 提示词）
```

## 文件说明

```
work-distill/
├── SKILL.md                  # skill 主文件（agent 读取的指引）
├── scripts/
│   ├── setup.py              # 初始化运行环境 + 修改配置
│   ├── sediment.py           # 核心：沉淀一条记录（写项目MD + 网页数据）
│   └── serve.py              # 本地网页服务 + 产出资料定位
└── templates/
    └── index.html            # 网页驾驶舱模板（成品，setup 时复制到运行环境）
```

## 项目 MD 示例（agent 的活说明书）

```markdown
# 内容沉淀skill
<!-- slug: content-distill | agent: zcode/glm-5.2 | ts: ... -->
<!-- goal: 做一个工作沉淀 skill | stage: 实现完成 -->

> agent 执行沉淀前先读本文件，了解项目现状再更新。

## 项目概况          ← 每次重写：目标/阶段/最新动态
## 当前焦点          ← 每次重写：下一步待办（优先级+进度）
## 更新历史          ← 追加：所有沉淀的时间线
```

## 多 agent 场景

同一项目在不同工具里被不同 agent 处理时：

- **slug 是聚合键**：同一项目无论在哪个工具，slug 必须一致
- **首次沉淀问用户定 slug**，之后沿用；不确定时 `sediment.py --list-projects` 查已有项目
- **显示名沿用已有**，不自己编，保证跨 agent 一致
- **goal/stage 首次写后不覆盖**，避免互相覆盖
- **next 自动去重**，避免重复沉淀同一待办

## 命令速查

```bash
# 初始化 / 改配置
python3 scripts/setup.py
python3 scripts/setup.py config

# 沉淀（agent 通常自动调用）
echo "正文" | python3 scripts/sediment.py --project "项目名" --project-slug "slug" \
  --type progress --summary "摘要" --agent "zcode/glm-5.2" \
  --next '[{"t":"待办","p":"高","prog":"50%"}]'

# 查已有项目（确认 slug）
python3 scripts/sediment.py --list-projects

# 查当前项目（压缩恢复）
python3 scripts/sediment.py --current

# 网页服务
python3 scripts/serve.py start
python3 scripts/serve.py status
python3 scripts/serve.py stop
```

## 技术要求

- Python 3.8+（仅标准库，无第三方依赖）
- macOS / Linux / Windows
- 任何支持加载 `~/.agents/skills/` 的 agent 工具（ZCode、Codex、Claude Code、Hermes 等）

## 设计原则

1. **项目 MD 是核心**——它是 agent 的活说明书，让多 agent 能接续上下文
2. **纯本地零依赖**——所有数据存本地一个目录，断网可用，无需任何外部服务
3. **网页设计固化**——index.html 是成品，换模型不变样
4. **token 友好**——禁读项目源码，按月分片懒加载
5. **身份确认交给用户**——agent 不猜项目身份，避免分裂

## License

MIT
