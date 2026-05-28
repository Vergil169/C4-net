# 意图驱动跨域网络自治系统

这是一个面向 “B-EP1 智能体互联网创新攻关赛项 / C4 网络技术挑战赛” 的可运行演示项目。系统提供 GUI 控制台和 FastAPI 后端，通过 LangChain + LangGraph ReAct 智能体完成网络意图解析、工具调用、策略生成、遥测验证和闭环自愈。

## 功能亮点

- LangGraph `create_react_agent` 驱动的 ReAct 智能体：思考、调用工具、观察、继续推理。
- DeepSeek OpenAI 兼容接口接入，优先读取 `DEEPSEEK_API_KEY`，禁止硬编码密钥。
- LangChain `@tool` 工具封装：意图解析、拓扑查询、遥测采集、路径规划、策略生成、SLA 验证、自愈重规划。
- 保持原有 Pydantic 数据模型和 JSON 输出格式，GUI 与 API 返回结构兼容旧版本。
- A2A 消息轨迹：展示智能体之间的协作过程。
- 跨域网络仿真：北京园区、天津骨干、济南骨干、上海云服务、广州灾备域。
- JSON 文件状态持久化：保存链路拥塞/故障状态、当前编排结果和最近 10 条意图记录。
- 无前端构建依赖：静态 HTML/CSS/JS 由 FastAPI 直接托管。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

可选：接入 DeepSeek。未配置时系统会保留本地演示降级。

```powershell
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
```

启动服务：

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

打开浏览器访问：

```text
http://127.0.0.1:8000
```

## 推荐演示输入

```text
请保障北京园区到上海云服务的视频会议业务，要求时延低于50ms，丢包率低于1%，优先避开拥塞链路。
```

演示步骤：

1. 在 GUI 中提交推荐意图。
2. 查看意图解析、任务流、A2A 消息、候选路径、配置片段和验证结果。
3. 点击 “模拟拥塞” 或 “模拟故障”。
4. 点击 “触发自愈”。
5. 观察系统重新选择路径并恢复 SLA。

## API

- `GET /api/state`：获取当前仿真状态、active result 和最近意图记录。
- `POST /api/intents`：提交自然语言意图并通过 ReAct 智能体执行完整编排。
- `POST /api/agent/intents`：显式智能体接口，输入与输出同 `/api/intents`。
- `POST /api/simulate`：模拟链路拥塞、故障或恢复。
- `POST /api/heal`：基于当前意图触发闭环自愈。
- `GET /api/agents`：查看智能体注册信息。
- `GET /api/mcp/tools`：查看 MCP 风格工具目录。
- `GET /api/a2a/messages`：查看最近一次编排产生的 A2A 消息。
- `GET /api/settings/llm`、`POST /api/settings/llm`：查看或保存 DeepSeek 连接设置。

示例：

```powershell
curl -X POST http://127.0.0.1:8000/api/agent/intents `
  -H "Content-Type: application/json" `
  -d "{\"text\":\"北京园区到上海云服务的视频会议业务，50ms 内，丢包小于1%。\"}"
```

## 架构说明

核心调度层位于 `app/agent.py`。系统使用 `create_react_agent` 绑定 DeepSeek 模型和所有 LangChain 工具。由于 LLM 输出不可信，FastAPI 最终响应不会直接使用模型文本，而是由工具上下文和 Pydantic 校验后的对象组装，确保输出结构与原系统一致。

`create_react_agent` 在 LangGraph 1.x 中已标记为 deprecated，本项目本轮升级按要求继续使用，并在代码中保留后续迁移到 `create_agent` 的注释入口。

状态持久化默认写入用户配置目录下的 `state.local.json`。可通过环境变量覆盖：

```powershell
$env:C4_STATE_FILE="D:\temp\c4-state.json"
```

## 项目结构

```text
app/
  main.py              FastAPI 入口和 API
  agent.py             LangGraph ReAct 智能体调度层
  agents.py            智能体注册表和确定性降级编排
  llm.py               DeepSeek LangChain 模型工厂
  tools.py             LangChain @tool 工具封装
  models.py            Pydantic 数据模型
  simulator.py         网络拓扑、遥测和策略仿真
  utils.py             JSON 状态保存与恢复
  static/
    index.html         GUI 控制台
    styles.css
    app.js
tests/
  test_agents.py
  test_api_settings.py
```

## 测试

```powershell
pytest
```

测试覆盖无 Key 降级、DeepSeek 配置安全性、工具独立调用、ReAct 接口兼容、链路状态恢复和最近意图记录截断。
