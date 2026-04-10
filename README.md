# ClawsCode

AI 编程助手命令行工具，在终端中与 AI 模型进行交互式对话，通过内置工具让 AI 自主完成编程任务。

## 功能特性

### 交互式 REPL

- 流式实时输出，AI 回复逐字渲染
- 思考过程展示（支持深度思考模型）
- Markdown 格式渲染
- 工具调用实时可视化
- 多行输入、历史记录、自动补全

### 内置工具

| 工具 | 功能 |
|------|------|
| **Bash** | 执行 Shell 命令，支持超时控制和工作目录指定 |
| **FileRead** | 读取文件内容，支持行号范围选择 |
| **FileEdit** | 精确字符串匹配替换，安全编辑文件 |
| **Glob** | Glob 模式文件搜索 |
| **Grep** | 正则表达式搜索文件内容 |

### MCP 协议支持

通过 Model Context Protocol 连接外部工具服务器，动态扩展 AI 能力。支持 stdio 传输方式，自动发现并加载远程工具。

### 权限系统

三级安全控制，所有工具执行前进行权限检查：

- **DENY** — 拒绝危险操作（如 `rm -rf /`）
- **ASK** — 需用户确认（默认）
- **ALLOW** — 直接放行

### 上下文自动压缩

基于 tiktoken 的 token 计数，当上下文接近窗口上限时自动压缩对话历史，保留关键信息，确保长对话稳定运行。

### 分层配置

配置按优先级从低到高合并：全局配置 → 项目配置 → 环境变量 → `.env` 文件 → 命令行参数。

## 安装

**使用 uv（推荐）：**

```bash
uv sync
```

**使用 pip：**

```bash
pip install -e .
```

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

## 技术栈

- **Python** >= 3.11
- **typer** — CLI 框架
- **openai** — LLM API 客户端（OpenAI 兼容协议）
- **rich** — 终端渲染（Markdown、实时输出）
- **prompt-toolkit** — 交互式输入
- **pydantic** — 数据验证
- **tiktoken** — Token 计数
- **mcp** — Model Context Protocol 客户端

## 许可证

MIT License
