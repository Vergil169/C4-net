# 意图驱动跨域网络自治系统

这是一个面向“智能体互联网 / C4 网络技术挑战”场景的可运行演示项目。系统通过自然语言输入业务意图，自动完成意图解析、任务拆解、拓扑感知、遥测采集、策略生成、配置下发模拟、闭环验证和故障自愈。

演示版本使用本地仿真数据，不依赖真实网络设备。后续可以把当前 MCP 风格工具替换为真实设备接口、Mininet、Containerlab、SDN 控制器或网络遥测平台。

## 核心能力

- **自然语言意图解析**：将业务诉求转换为结构化 `BusinessIntent`，提取源站点、目标站点、业务类型、时延、丢包、带宽、优先级和约束。
- **多智能体协作**：使用 Intent、Planner、Topology、Telemetry、Policy、Verification、Healing 等 Agent 展示 A2A 协作链路。
- **MCP 风格工具接口**：封装拓扑查询、遥测采集、路径规划、策略生成、SLA 验证和自愈重规划能力。
- **策略生成与下发模拟**：根据当前拓扑和遥测生成路径、QoS、ACL、路由规则和配置预览，并以 dry-run 方式模拟策略下发。
- **闭环验证**：策略生成后由 Verification Agent 基于遥测数据验证意图是否达成。
- **自动自愈**：验证失败、链路拥塞或故障时，自动触发 Healing Agent 避开退化链路并重新验证。
- **GUI 演示控制台**：展示结构化意图、任务流、A2A 消息、拓扑、策略、遥测、验证结果和自愈轨迹。
- **本地状态持久化**：保存链路状态、活跃编排结果和最近 10 条意图记录。

## 闭环验证能力

赛项要求强调“网络意图自动翻译与闭环验证”，并要求通过遥测持续评估意图达成状态。当前项目的闭环链路为：

```text
自然语言意图
  -> Intent Agent 解析 SLA
  -> Planner Agent 拆解任务流
  -> Topology Agent 查询跨域拓扑
  -> Telemetry Agent 采集链路时延、丢包率、利用率和健康状态
  -> Policy Agent 生成路径、QoS、ACL 和配置片段
  -> Network Simulator 模拟策略下发
  -> Verification Agent 对比 SLA 与遥测结果
  -> 未达成时触发 Healing Agent 重规划
  -> Verification Agent 二次验证
```

Verification Agent 会验证：

- 端到端时延是否低于 `max_latency_ms`
- 端到端丢包率是否低于 `max_loss_percent`
- 路径瓶颈带宽是否满足 `min_bandwidth_mbps`
- 已选链路是否存在拥塞、故障或高利用率
- 当前策略是否存在无法满足意图的风险

GUI 的“验证结果”面板会直接展示“SLA 要求 vs 遥测实测值 vs 余量”。如果验证失败，系统会在 A2A 消息和自愈轨迹中展示从 Verification Agent 到 Healing Agent 的告警、重规划、路径切换和二次验证结果。

## 智能体角色

- **Intent Agent**：解析自然语言业务诉求，生成结构化意图。
- **Planner Agent**：将意图拆解为跨域网络任务流。
- **Topology Agent**：维护跨域网络拓扑和链路状态。
- **Telemetry Agent**：采集链路时延、丢包率、利用率和故障状态。
- **Policy Agent**：生成路径、QoS、ACL、路由规则和配置预览。
- **Verification Agent**：在策略下发模拟后验证连通性、SLA 和策略风险。
- **Healing Agent**：在拥塞、故障或 SLA 未达成时触发重规划和策略修复。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

可选：配置 DeepSeek API Key。未配置时系统会使用本地规则降级解析，仍可完整演示闭环流程。

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

也可以运行桌面封装：

```powershell
python desktop.py
```

## 推荐演示脚本

### 1. 普通意图闭环验证

输入：

```text
请保障北京园区到上海云服务的视频会议业务，要求时延低于50ms，丢包率低于1%，带宽至少100M，优先避开拥塞链路。
```

观察点：

- Intent Agent 提取视频会议、北京到上海、50ms、1%、100M。
- Policy Agent 生成路径、QoS 和配置预览。
- Verification Agent 对比遥测值与 SLA，结果为 `achieved`。
- 验证面板展示时延、丢包、带宽和利用率的达成证据。

### 2. 严格 SLA 触发自动自愈

输入：

```text
请保障北京园区到上海云服务的视频会议业务，要求时延低于30ms，丢包率低于1%，带宽至少100M，优先选择低时延路径。
```

观察点：

- 主路径验证失败或余量不足。
- Verification Agent 自动触发 Healing Agent。
- Healing Agent 切换到低时延专线。
- 自愈轨迹最后一步展示二次 SLA 验证通过。

### 3. 拥塞/故障后闭环修复

操作：

1. 先提交一条业务意图。
2. 点击“模拟拥塞”或“模拟故障”。
3. 查看系统是否自动重新验证当前策略。
4. 如果当前路径不再满足 SLA，系统会自动触发自愈并重新规划路径。

观察点：

- Telemetry Agent 更新链路健康状态。
- Verification Agent 发现当前策略不再满足意图。
- Healing Agent 避开退化链路。
- Verification Agent 对新策略进行二次验证。

## API

- `GET /api/state`：获取当前仿真状态、活跃编排结果和最近意图记录。
- `POST /api/intents`：提交自然语言意图并执行完整编排。
- `POST /api/agent/intents`：兼容智能体接口，输入输出与 `/api/intents` 一致。
- `POST /api/intents/optimize`：优化自然语言意图表达。
- `POST /api/simulate`：模拟链路拥塞、故障或恢复。
- `POST /api/heal`：基于当前意图触发闭环自愈。
- `GET /api/agents`：查看智能体注册信息。
- `GET /api/mcp/tools`：查看 MCP 风格工具目录。
- `GET /api/a2a/messages`：查看最近一次编排产生的 A2A 消息。
- `GET /api/settings/llm`、`POST /api/settings/llm`：查看或保存 DeepSeek 连接设置。
- `POST /api/settings/llm/test`：测试模型连接。

示例：

```powershell
curl -X POST http://127.0.0.1:8000/api/intents `
  -H "Content-Type: application/json" `
  -d "{\"text\":\"请保障北京园区到上海云服务的视频会议业务，要求时延低于50ms，丢包率低于1%，带宽至少100M。\"}"
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
  simulator.py         网络拓扑、遥测、策略和验证仿真
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

现有测试覆盖：

- 本地规则解析和 DeepSeek 配置降级
- 策略生成与 SLA 验证
- 严格 SLA 下自动自愈
- 拥塞、故障和无可行路径场景
- LangChain 工具 JSON 输出
- 状态持久化和最近意图记录截断

## 设计说明

核心调度层位于 `app/agent.py` 和 `app/agents.py`。系统优先尝试 LangGraph ReAct 智能体；当模型不可用时，会回退到确定性编排，保证演示稳定性。

FastAPI 最终响应不直接信任大模型自由文本，而是使用工具上下文和 Pydantic 校验后的对象组装 `OrchestrationResult`，确保 GUI 和 API 返回结构稳定。

当前策略下发是 dry-run 模拟：`NetworkPolicy.config_preview` 展示拟下发配置，`VerificationResult` 展示策略是否满足业务意图。真实设备接入时，可以将 dry-run 替换为控制器 northbound API 或设备配置接口，并保留现有 Verification Agent 的闭环验证流程。
