# 意图驱动跨域网络自治系统

这是一个面向 “B-EP1 智能体互联网创新攻关赛项 / C4 网络技术挑战赛” 的可运行演示项目。系统实现了一个 GUI 控制台和 FastAPI 后端，用于展示多智能体协同完成网络意图解析、策略生成、仿真下发、遥测验证和自动自愈。

## 功能亮点

- 自然语言业务意图解析为结构化 JSON。
- 多智能体任务编排：Intent、Planner、Topology、Telemetry、Policy、Verification、Healing。
- A2A 消息轨迹：展示智能体之间的协作过程。
- MCP 风格工具接口：拓扑查询、遥测采集、策略生成、配置执行、闭环验证。
- 跨域网络仿真：北京园区、天津骨干、济南骨干、上海云服务、广州灾备域。
- 闭环自愈演示：可模拟链路拥塞/故障并自动重规划。
- 无前端构建依赖：静态 HTML/CSS/JS 由 FastAPI 直接托管。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
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
4. 点击 “触发闭环自愈”。
5. 观察系统重新选择路径并恢复 SLA。

## API

- `GET /api/state`：获取当前仿真状态。
- `POST /api/intents`：提交自然语言意图并执行完整 Agent 编排。
- `POST /api/simulate`：模拟链路拥塞、故障或恢复。
- `POST /api/heal`：基于当前意图触发闭环自愈。
- `GET /api/agents`：查看智能体注册信息。
- `GET /api/mcp/tools`：查看 MCP 风格工具目录。
- `GET /api/a2a/messages`：查看最近一次编排产生的 A2A 消息。

## 项目结构

```text
app/
  main.py              FastAPI 入口和 API
  agents.py            多智能体实现
  models.py            Pydantic 数据模型
  simulator.py         网络拓扑、遥测和策略仿真
  static/
    index.html         GUI 控制台
    styles.css
    app.js
tests/
  test_agents.py
```

## 说明

演示版本默认使用规则引擎模拟 LLM 行为，保证离线稳定。若接入真实大模型，可在 `IntentAgent` 和 `PlannerAgent` 中替换为 LangChain/LangGraph 调用，并复用现有结构化输入输出模型。
