# ClawsCode

AI 编程助手命令行工具，在终端中与 AI 模型进行交互式对话，通过内置工具让 AI 自主完成编程任务。

## 功能特性

### 交互式 REPL

- 流式实时输出，AI 回复逐字渲染
- 思考过程展示（支持深度思考模型）
- Markdown 格式渲染
- 工具调用实时可视化
- 多行输入、历史记录、自动补全

### 内置工具（44 个）

| 类别 | 工具 | 功能 |
|------|------|------|
| 文件操作 | FileRead, FileEdit, FileWrite, NotebookEdit | 读取、编辑、写入文件 |
| 搜索 | Glob, Grep, ToolSearch | 文件搜索、内容搜索、工具检索 |
| 命令执行 | Bash, PowerShell | Shell 命令执行，支持超时和工作目录 |
| 网络 | WebFetch, WebSearch | 网页抓取、网络搜索 |
| 任务管理 | TodoWrite, Brief, SleepTool | 任务列表、摘要、定时等待 |
| 交互 | AskUserQuestion, SendMessage | 用户交互、Agent 间通信 |
| Agent 系统 | Agent, TaskOutput, TaskStop | 子 Agent 调度与管理 |
| 多 Agent | TeamCreate, TeamDelete, TeamList, SwarmDispatch | 多 Agent 团队协作 |
| 浏览器控制 | Screenshot, MouseClick, MouseMove, Drag, Scroll, Keyboard, Navigate, Launch, Connect, Shutdown | 完整浏览器自动化 |
| MCP 协议 | McpAuth, ListMcpResources, ReadMcpResource | 外部工具服务器集成 |
| 定时任务 | CronCreate, CronDelete, CronList | 定时任务调度 |
| IDE 集成 | LSPTool | LSP 协议客户端（诊断、跳转定义） |
| 配置 | ConfigTool, EnterPlanMode, ExitPlanMode | 配置管理与计划模式 |
| 技能 | SkillTool | 动态加载技能 |

### MCP 协议支持

通过 Model Context Protocol 连接外部工具服务器，动态扩展 AI 能力。支持 stdio 传输方式，自动发现并加载远程工具。

### 权限系统

四级安全控制，所有工具执行前进行权限检查：

- **DENY** — 拒绝危险操作（如 `rm -rf /`）
- **ASK** — 需用户确认（默认）
- **ALLOW** — 直接放行
- **AUTO** — 自动分类（Bash 命令安全度检测）

支持 Plan 模式（只读工具白名单）和 BYPASS 模式（全部放行）。

### 上下文自动压缩

双层压缩策略，确保长对话稳定运行：

- **LLM 压缩**：调用 LLM 生成 9 部分结构化摘要，保留关键信息
- **截断降级**：LLM 压缩失败时自动降级到保留最近 N 条消息
- 连续失败 3 次后锁定降级模式

### 多 Agent 协作

- **Coordinator**：协调者 Agent 自动拆分任务、分配子 Agent、汇总结果
- **Swarm**：多 Agent 并发执行，支持团队创建和管理
- **内置 Agent**：explore（探索）、general（通用）、plan（规划）、verification（验证）

### Hook 系统

11 种事件类型的观察者系统，支持 3 种 Hook 类型：

- **Prompt Hook**：执行命令行命令
- **HTTP Hook**：发送 HTTP 请求
- **Agent Hook**：启动子 Agent

Hook 可通过 `should_block` 拦截工具调用。

## 安装

```bash
# 使用 uv（推荐）
uv sync

# 使用 pip
pip install -e .
```

要求 Python >= 3.11。

## 快速开始

### 1. 配置 API Key

在项目根目录创建 `.env` 文件：

```
API_KEY=your_api_key_here
MODEL=ZhipuAI/GLM-5
```

或设置环境变量 `CLAWSCODE_API_KEY`。

### 2. 启动

```bash
# 交互模式
clawscode

# 带 initial prompt 启动
clawscode "帮我分析这个项目"

# 非交互模式，输出结果后退出
clawscode "解释这段代码" --print

# 指定模型
clawscode --model Qwen/Qwen3-235B-A22B

# 恢复上次会话
clawscode --resume latest
```

### 3. REPL 内置命令

| 命令 | 功能 |
|------|------|
| `/help` | 显示可用命令 |
| `/clear` | 清除对话历史 |
| `/config` | 显示当前配置 |
| `/compact` | 手动触发上下文压缩 |
| `/model [名称]` | 查看或切换模型 |
| `/mcp [list]` | 查看 MCP 服务器状态或工具列表 |

## 配置

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CLAWSCODE_API_KEY` / `API_KEY` | API 密钥 | — |
| `CLAWSCODE_BASE_URL` | API 地址 | `https://api-inference.modelscope.cn/v1` |
| `CLAWSCODE_MODEL` / `MODEL` | 模型名称 | `ZhipuAI/GLM-5` |
| `CLAWSCODE_MAX_TOKENS` | 最大 token 数 | `128000` |
| `CLAWSCODE_PERMISSION_MODE` | 权限模式 | `default` |

### 配置文件

配置按优先级从低到高合并：全局配置 → 项目配置 → 环境变量 → `.env` 文件 → 命令行参数。

- 全局配置：`~/.clawscode/settings.json`
- 项目配置：`<project>/.clawscode/settings.json`

### MCP 服务器配置

在项目配置文件中添加 MCP 服务器：

```json
{
  "mcp_servers": {
    "server-name": {
      "command": "npx",
      "args": ["-y", "@some/mcp-server"]
    }
  }
}
```

### Hook 配置

```json
{
  "hooks": {
    "enabled": true,
    "hooks": [
      {
        "name": "audit",
        "event": "PostToolUse",
        "type": "http",
        "url": "http://localhost:8080/hook"
      }
    ]
  }
}
```

## 项目结构

```
src/
├── cli.py                    # CLI 入口
├── repl.py                   # REPL 交互循环 + 终端渲染
├── query.py                  # 查询分发
├── query_engine.py           # 核心 Agent 循环引擎
├── api_client.py             # LLM API 流式通信
├── tool.py                   # 工具抽象基类
├── state.py                  # 全局状态（Settings + AppState）
├── config.py                 # 分层配置加载
├── context.py                # 系统 Prompt 构建
├── compact.py                # 上下文压缩门面
├── permissions.py            # 权限检查系统
├── commands.py               # REPL 内置命令
├── tools/                    # 44 个工具实现
├── services/                 # 基础设施服务（压缩、MCP、会话等）
├── agents/                   # Agent 系统（Coordinator + Swarm）
├── hooks/                    # Hook 观察者系统
├── skills/                   # 技能系统（7 个内置技能）
├── plugins/                  # 插件系统
└── utils/                    # Git 操作、配置工具
```

## 技术栈

| 库 | 用途 |
|----|------|
| **typer** | CLI 框架 |
| **openai** | LLM API 客户端（OpenAI 兼容协议） |
| **rich** | 终端渲染（Markdown、实时输出） |
| **prompt-toolkit** | 交互式输入 |
| **pydantic** | 数据验证 |
| **tiktoken** | Token 计数 |
| **mcp** | Model Context Protocol 客户端 |
| **httpx** | HTTP 客户端 |
| **websockets** | WebSocket 通信 |
| **asyncssh** | SSH 远程执行 |

## 许可证

MIT License
