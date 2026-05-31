const nodePositions = {
  "beijing-campus": [8, 42],
  "tianjin-core": [31, 23],
  "jinan-core": [56, 28],
  "shanghai-cloud": [78, 45],
  "guangzhou-dr": [48, 70],
  "nanjing-edge": [61, 60],
};

const promptExamples = [
  {
    category: "realtime",
    tags: ["实时协同", "关键业务"],
    title: "保障视频会议体验",
    description: "适用于高管会议、跨园区协作、云会议质量保障。",
    text: "北京园区到上海云服务的视频会议业务，需要低时延路径，50ms 内，丢包小于1%，带宽至少100M，优先避开拥塞链路。",
  },
  {
    category: "realtime",
    tags: ["实时协同", "语音"],
    title: "保障语音客服质量",
    description: "适用于 VoIP/SIP、呼叫中心和语音专线体验优化。",
    text: "华北接入域到华东云域的语音客服业务需要稳定低抖动，丢包不超过0.5%，优先选择低时延链路，链路异常时自动切换。",
  },
  {
    category: "finance",
    tags: ["金融交易", "关键业务"],
    title: "核心交易专线保障",
    description: "适用于支付、订单、核心交易等高优先级业务。",
    text: "北京园区到上海云服务的核心交易专线需要安全优先，必须强隔离并拒绝异常流量，时延控制在30ms内，丢包低于0.2%，带宽500M。",
  },
  {
    category: "dr",
    tags: ["灾备与备份", "高优先级"],
    title: "夜间灾备同步",
    description: "适用于备份窗口、跨域数据同步和灾备链路保障。",
    text: "北京园区夜间向广州灾备域同步备份数据，需要大带宽和故障避让，带宽至少800M，不要求特别低时延，但要避开故障链路。",
  },
  {
    category: "healing",
    tags: ["故障自愈", "拥塞避让"],
    title: "拥塞后自动绕行",
    description: "适用于主路径拥塞或故障后的自动切线演示。",
    text: "北京园区到上海云服务的关键业务在主链路拥塞或故障时，系统后台自动判断并切换到北京-济南-上海低时延备用专线，无需人工操作。",
  },
  {
    category: "security",
    tags: ["安全合规", "隔离"],
    title: "敏感业务隔离",
    description: "适用于敏感流量隔离、异常流量拒绝和合规保障。",
    text: "北京园区到上海云服务的敏感业务需要安全合规优先，隔离普通业务流量，拒绝异常流量，丢包低于1%，带宽200M。",
  },
  {
    category: "capacity",
    tags: ["容量优化", "扩容"],
    title: "临时带宽扩容",
    description: "适用于活动保障、突发流量和临时容量提升。",
    text: "北京园区到上海云服务临时需要带宽扩容，保障业务带宽不少于1000M，优先选择低利用率链路，避免影响实时业务。",
  },
  {
    category: "ops",
    tags: ["运维巡检", "健康检查"],
    title: "跨域链路健康巡检",
    description: "适用于例行巡检、链路健康验证和风险发现。",
    text: "请对北京园区到上海云服务的跨域链路做健康巡检，检查时延、丢包、利用率和故障状态，发现拥塞后给出绕行策略。",
  },
];

let currentState = null;
let deepSeekPromptShown = false;
let lastSimulatedLinkId = null;

const els = {
  agents: document.querySelector("#agents"),
  apiKey: document.querySelector("#apiKey"),
  bandwidthSla: document.querySelector("#bandwidthSla"),
  baseUrl: document.querySelector("#baseUrl"),
  closeSettings: document.querySelector("#closeSettings"),
  confidence: document.querySelector("#confidence"),
  healIntent: document.querySelector("#healIntent"),
  healingAlert: document.querySelector("#healingAlert"),
  healingSummary: document.querySelector("#healingSummary"),
  healingTrace: document.querySelector("#healingTrace"),
  intentInput: document.querySelector("#intentInput"),
  intentJson: document.querySelector("#intentJson"),
  latencySla: document.querySelector("#latencySla"),
  messages: document.querySelector("#messages"),
  modelName: document.querySelector("#modelName"),
  openSettings: document.querySelector("#openSettings"),
  optimizeIntent: document.querySelector("#optimizeIntent"),
  parseNote: document.querySelector("#parseNote"),
  promptFilter: document.querySelector("#promptFilter"),
  promptLibrary: document.querySelector("#promptLibrary"),
  promptSearch: document.querySelector("#promptSearch"),
  parseSource: document.querySelector("#parseSource"),
  parserBadge: document.querySelector("#parserBadge"),
  policy: document.querySelector("#policy"),
  recoverLink: document.querySelector("#recoverLink"),
  saveSettings: document.querySelector("#saveSettings"),
  selectedPath: document.querySelector("#selectedPath"),
  settingsDialog: document.querySelector("#settingsDialog"),
  settingsStatus: document.querySelector("#settingsStatus"),
  simulateCongestion: document.querySelector("#simulateCongestion"),
  simulateFailure: document.querySelector("#simulateFailure"),
  statusPill: document.querySelector("#statusPill"),
  submitIntent: document.querySelector("#submitIntent"),
  tasks: document.querySelector("#tasks"),
  telemetry: document.querySelector("#telemetry"),
  testModel: document.querySelector("#testModel"),
  timeoutSeconds: document.querySelector("#timeoutSeconds"),
  topology: document.querySelector("#topology"),
  verification: document.querySelector("#verification"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

function setBusy(isBusy, label = "处理中") {
  document.querySelectorAll("button").forEach((button) => {
    button.disabled = isBusy;
  });
  if (isBusy) {
    els.statusPill.textContent = label;
  }
}

function renderState(state) {
  currentState = state;
  renderAgents(state.agents);
  renderTopology(state.nodes, state.links, state.active_result?.policy?.selected_links || []);
  renderTelemetry(state.telemetry);
  if (state.active_result) {
    renderResult(state.active_result);
  } else {
    renderHealingTrace([]);
  }
}

function renderPromptLibrary() {
  const filter = els.promptFilter.value;
  const keyword = els.promptSearch.value.trim().toLowerCase();
  const examples = promptExamples.filter((item) => {
    const inCategory = filter === "all" || item.category === filter;
    const haystack = `${item.title} ${item.description} ${item.tags.join(" ")} ${item.text}`.toLowerCase();
    return inCategory && (!keyword || haystack.includes(keyword));
  });
  els.promptLibrary.innerHTML = examples
    .map((item, index) => `
      <article class="prompt-card">
        <div class="prompt-tags">${item.tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}</div>
        <strong>${escapeHtml(item.title)}</strong>
        <p>${escapeHtml(item.description)}</p>
        <div class="prompt-actions">
          <button class="ghost" data-prompt-index="${index}" data-prompt-action="fill">填入</button>
          <button data-prompt-index="${index}" data-prompt-action="submit">直接提交</button>
        </div>
      </article>
    `)
    .join("") || `<div class="prompt-card"><strong>没有匹配结果</strong><p>换个关键词试试，例如“交易”“灾备”“拥塞”。</p></div>`;

  els.promptLibrary.querySelectorAll("[data-prompt-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const item = examples[Number(button.dataset.promptIndex)];
      els.intentInput.value = item.text;
      els.intentInput.focus();
      if (button.dataset.promptAction === "submit") {
        await submitCurrentIntent();
      }
    });
  });
}

function renderResult(result) {
  els.statusPill.textContent = statusText(result.status, result.healed);
  els.intentJson.textContent = JSON.stringify(result.intent, null, 2);
  renderIntentSummary(result.intent);
  renderTasks(result.tasks);
  renderMessages(result.messages);
  renderPolicy(result.policy);
  renderVerification(result.verification);
  renderHealingTrace(result.healing_trace || [], result);
  renderTopology(result.nodes, result.links, result.policy.selected_links);
  els.selectedPath.textContent = result.policy.path.join(" -> ");
}

function renderHealingTrace(trace, result = null) {
  const steps = trace || [];
  if (!els.healingTrace || !els.healingAlert || !els.healingSummary) return;
  if (!steps.length) {
    els.healingSummary.textContent = "暂无自愈事件";
    els.healingAlert.textContent = "等待 SLA 告警";
    els.healingAlert.className = "healing-alert";
    els.healingTrace.innerHTML = "";
    return;
  }
  const failed = result?.verification && !result.verification.passed;
  const warning = result?.verification?.severity === "warning";
  els.healingSummary.textContent = failed ? "自愈失败" : warning ? "自愈完成（指标临界）" : "自愈完成";
  els.healingAlert.textContent = failed
    ? "自愈重试达到上限，未找到可行路径"
    : warning
      ? "检测到 SLA 不达标，已自动触发自愈；当前指标接近阈值，持续监控"
      : "检测到 SLA 不达标，已自动触发自愈流程";
  els.healingAlert.className = `healing-alert ${failed ? "bad" : warning ? "warn" : "ok"}`;
  els.healingTrace.innerHTML = steps
    .map((step) => {
      const metrics = Object.entries(step.metrics || {})
        .map(([key, value]) => `<span>${escapeHtml(key)}: ${escapeHtml(value)}</span>`)
        .join("");
      const links = (step.links || []).map(escapeHtml).join(" / ");
      return `
        <div class="healing-step ${escapeHtml(step.status)}">
          <b>${step.stage}</b>
          <div>
            <strong>${escapeHtml(step.name)}</strong>
            <p>${escapeHtml(step.detail)}</p>
            <div class="healing-meta">${metrics}${links ? `<span>${links}</span>` : ""}</div>
          </div>
        </div>
      `;
    })
    .join("");
}

function renderIntentSummary(intent) {
  const isDeepSeek = intent.parse_source === "deepseek";
  els.parserBadge.textContent = isDeepSeek ? "DeepSeek 解析" : "本地规则解析";
  els.parserBadge.className = `parser-badge ${isDeepSeek ? "ai" : "fallback"}`;
  els.parseSource.textContent = isDeepSeek ? "DeepSeek" : "本地规则";
  els.confidence.textContent = `${Math.round((intent.confidence || 0) * 100)}%`;
  els.latencySla.textContent = `${intent.max_latency_ms}ms / ${intent.max_loss_percent}%`;
  els.bandwidthSla.textContent = `${intent.min_bandwidth_mbps} Mbps`;
  els.parseNote.textContent = intent.parse_note || "结构化解析完成";
}

function renderAgents(agents) {
  els.agents.innerHTML = agents
    .map((agent) => `
      <div class="agent">
        <strong>${escapeHtml(agent.name)}</strong>
        <span>${escapeHtml(agent.role)} · ${agent.capabilities.map(escapeHtml).join(" / ")}</span>
      </div>
    `)
    .join("");
}

function renderTasks(tasks) {
  els.tasks.innerHTML = tasks
    .map((task) => `
      <div class="task">
        <strong>${escapeHtml(task.id)} · ${escapeHtml(task.agent)}</strong>
        <span>${escapeHtml(task.action)} · ${escapeHtml(task.detail)}</span>
      </div>
    `)
    .join("");
}

function renderMessages(messages) {
  els.messages.innerHTML = messages
    .map((message) => `
      <div class="message">
        <strong>${escapeHtml(message.sender)} -> ${escapeHtml(message.receiver)}</strong>
        <span>${escapeHtml(message.performative)} · ${escapeHtml(shortPayload(message.payload))}</span>
      </div>
    `)
    .join("");
}

function renderPolicy(policy) {
  if (!policy) {
    els.policy.textContent = "暂无策略";
    return;
  }
  els.policy.innerHTML = `
    <div class="policy-block"><strong>${escapeHtml(policy.policy_id)}</strong><br />${escapeHtml(policy.qos_class)} · ${policy.bandwidth_reservation_mbps} Mbps</div>
    <div class="policy-block"><strong>路径</strong><br />${policy.path.map(escapeHtml).join(" -> ")}</div>
    <div class="policy-block"><strong>ACL</strong><br />${policy.acl_rules.map(escapeHtml).join("<br />")}</div>
    <div class="policy-block"><strong>配置预览</strong>${policy.config_preview.map((line) => `<code>${escapeHtml(line)}</code>`).join("")}</div>
  `;
}

function renderVerification(result) {
  if (!result) {
    els.verification.innerHTML = "";
    return;
  }
  const cls = result.passed ? "ok" : "bad";
  const issues = (result.issues || []).map((issue) => `<code>${escapeHtml(issue)}</code>`).join("");
  els.verification.innerHTML = `
    <div class="metric ${cls}"><span>状态</span><strong>${escapeHtml(result.status)}</strong></div>
    <div class="metric ${cls}"><span>结果</span><strong>${result.passed ? "通过" : "需处理"}</strong></div>
    <div class="metric"><span>端到端时延</span><strong>${result.latency_ms}ms</strong></div>
    <div class="metric"><span>丢包率</span><strong>${result.loss_percent}%</strong></div>
    <div class="metric"><span>瓶颈利用率</span><strong>${result.bottleneck_utilization_percent}%</strong></div>
    ${issues ? `<div class="metric wide"><span>问题</span><strong>${issues}</strong></div>` : ""}
    <div class="metric wide"><span>建议</span><strong>${escapeHtml(result.recommendation)}</strong></div>
  `;
}

function renderTelemetry(telemetry) {
  els.telemetry.innerHTML = telemetry
    .map((item) => `
      <div class="metric ${item.health === "normal" ? "ok" : "bad"}">
        <span>${escapeHtml(item.link_id)}</span>
        <strong>${healthText(item.health)}</strong>
        <span>${item.latency_ms}ms · ${item.loss_percent}% · ${item.utilization_percent}%</span>
      </div>
    `)
    .join("");
}

function renderTopology(nodes, links, selectedLinks) {
  const width = els.topology.clientWidth || 900;
  const height = els.topology.clientHeight || 310;
  const nodeMarkup = nodes
    .map((node) => {
      const [x, y] = nodePositions[node.id] || [50, 50];
      return `<div class="node" style="left:${x}%; top:${y}%">${escapeHtml(node.label)}<br /><small>${escapeHtml(node.domain)}</small></div>`;
    })
    .join("");
  const linkMarkup = links
    .map((link) => {
      const [x1p, y1p] = nodePositions[link.source];
      const [x2p, y2p] = nodePositions[link.target];
      const x1 = (x1p / 100) * width + 62;
      const y1 = (y1p / 100) * height + 27;
      const x2 = (x2p / 100) * width + 62;
      const y2 = (y2p / 100) * height + 27;
      const length = Math.hypot(x2 - x1, y2 - y1);
      const angle = Math.atan2(y2 - y1, x2 - x1) * 180 / Math.PI;
      const selected = selectedLinks.includes(link.id) ? "selected" : "";
      const normalizedType = link.link_type === "dedicated" ? "low_latency_dedicated" : link.link_type;
      const typeClass = normalizedType || "backbone";
      const labelX = (x1 + x2) / 2;
      const labelY = (y1 + y2) / 2;
      const typeLabel = normalizedType === "low_latency_dedicated" ? "低时延专线" : "骨干中转";
      return `
        <div class="link ${typeClass} ${selected} ${link.health}" style="left:${x1}px; top:${y1}px; width:${length}px; transform:rotate(${angle}deg)"></div>
        <div class="link-label" style="left:${labelX}px; top:${labelY}px">${link.latency_ms}ms / ${link.loss_percent}% / ${link.capacity_mbps}M <span class="link-type">${typeLabel}</span></div>
      `;
    })
    .join("");
  els.topology.innerHTML = linkMarkup + nodeMarkup;
}

async function loadSettings() {
  const settings = await api("/api/settings/llm");
  els.modelName.value = settings.model;
  els.baseUrl.value = settings.base_url;
  els.timeoutSeconds.value = settings.timeout;
  els.settingsStatus.textContent = settings.configured ? "DeepSeek API Key 已配置" : "DeepSeek API Key 未配置";
  if (!settings.configured && !deepSeekPromptShown && !localStorage.getItem("deepseekPromptDismissed")) {
    deepSeekPromptShown = true;
    const openDialog = window.confirm("当前未配置 DeepSeek API Key。是否现在接入？取消后系统会继续使用本地演示降级。");
    if (openDialog) {
      els.settingsDialog.showModal();
    } else {
      localStorage.setItem("deepseekPromptDismissed", "1");
    }
  }
}

async function saveSettings() {
  const result = await api("/api/settings/llm", {
    method: "POST",
    body: JSON.stringify({
      api_key: els.apiKey.value.trim(),
      model: els.modelName.value.trim(),
      base_url: els.baseUrl.value.trim(),
      timeout: Number(els.timeoutSeconds.value || 12),
    }),
  });
  els.apiKey.value = "";
  els.settingsStatus.textContent = result.configured ? "设置已保存" : "设置已保存，但 API Key 为空";
}

async function testSettings() {
  els.settingsStatus.textContent = "正在测试连接...";
  const result = await api("/api/settings/llm/test", { method: "POST" });
  els.settingsStatus.textContent = result.message;
}

function shortPayload(payload) {
  const raw = JSON.stringify(payload);
  return raw.length > 96 ? `${raw.slice(0, 96)}...` : raw;
}

function healthText(health) {
  return {
    normal: "正常",
    congested: "拥塞",
    failed: "故障",
  }[health] || health;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function statusText(status, healed) {
  if (healed) return "自愈完成";
  const map = {
    pending: "等待意图",
    achieved: "意图达成",
    partial: "部分达成",
    conflict: "策略冲突",
    failed: "执行失败",
    healing: "自愈中",
  };
  return map[status] || status;
}

async function refresh() {
  renderState(await api("/api/state"));
}

async function runAction(label, action, successLabel = "操作完成") {
  try {
    setBusy(true, label);
    const result = await action();
    if (result?.active_result) {
      renderResult(result.active_result);
    }
    await refresh();
    els.statusPill.textContent = result?.healing_triggered ? statusText(result.active_result.status, result.active_result.healed) : successLabel;
  } catch (error) {
    els.statusPill.textContent = "操作失败";
    els.parseNote.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

function linkExists(linkId) {
  return Boolean((currentState?.active_result?.links || currentState?.links || []).some((link) => link.id === linkId));
}

function selectSimulationLink({ preferDegraded = false } = {}) {
  const links = currentState?.active_result?.links || currentState?.links || [];
  if (!links.length) {
    throw new Error("当前拓扑还未加载，请稍后再试。");
  }
  if (preferDegraded) {
    const degraded = links.find((link) => link.health !== "normal");
    if (degraded) return degraded.id;
    if (lastSimulatedLinkId && linkExists(lastSimulatedLinkId)) return lastSimulatedLinkId;
  }
  const selectedLinks = currentState?.active_result?.policy?.selected_links || [];
  const selected = selectedLinks.find((linkId) => linkExists(linkId));
  if (selected) return selected;
  return links[0].id;
}

async function submitCurrentIntent() {
  try {
    setBusy(true, "解析中");
    const result = await api("/api/intents", {
      method: "POST",
      body: JSON.stringify({ text: els.intentInput.value }),
    });
    renderResult(result);
    await refresh();
  } catch (error) {
    els.statusPill.textContent = "提交失败";
    els.parseNote.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

els.submitIntent.addEventListener("click", submitCurrentIntent);

els.optimizeIntent.addEventListener("click", async () => {
  try {
    setBusy(true, "优化输入中");
    const result = await api("/api/intents/optimize", {
      method: "POST",
      body: JSON.stringify({ text: els.intentInput.value }),
    });
    els.intentInput.value = result.optimized_text;
    els.parseNote.textContent = result.note;
    els.parserBadge.textContent = result.source === "deepseek" ? "DeepSeek 优化" : "本地优化";
    els.parserBadge.className = `parser-badge ${result.source === "deepseek" ? "ai" : "fallback"}`;
    els.statusPill.textContent = "输入已优化";
  } catch (error) {
    els.statusPill.textContent = "优化失败";
    els.parseNote.textContent = error.message;
  } finally {
    setBusy(false);
  }
});

els.simulateCongestion.addEventListener("click", async () => {
  await runAction("模拟拥塞中", () => {
    const linkId = selectSimulationLink();
    lastSimulatedLinkId = linkId;
    return api("/api/simulate", {
      method: "POST",
      body: JSON.stringify({ action: "congest", link_id: linkId }),
    });
  }, "已模拟拥塞并自动切线");
});

els.simulateFailure.addEventListener("click", async () => {
  await runAction("模拟故障中", () => {
    const linkId = selectSimulationLink();
    lastSimulatedLinkId = linkId;
    return api("/api/simulate", {
      method: "POST",
      body: JSON.stringify({ action: "fail", link_id: linkId }),
    });
  }, "已模拟故障并自动切线");
});

els.recoverLink.addEventListener("click", async () => {
  await runAction("恢复链路中", () => {
    const linkId = selectSimulationLink({ preferDegraded: true });
    return api("/api/simulate", {
      method: "POST",
      body: JSON.stringify({ action: "recover", link_id: linkId }),
    });
  }, "链路已恢复");
});

els.healIntent.addEventListener("click", async () => {
  try {
    setBusy(true, "自愈中");
    const result = await api("/api/heal", { method: "POST" });
    renderResult(result);
    await refresh();
  } catch (error) {
    els.statusPill.textContent = "自愈失败";
    els.parseNote.textContent = error.message;
  } finally {
    setBusy(false);
  }
});

els.openSettings.addEventListener("click", async () => {
  await loadSettings();
  els.settingsDialog.showModal();
});

els.closeSettings.addEventListener("click", () => {
  els.settingsDialog.close();
});

els.saveSettings.addEventListener("click", async () => {
  try {
    await saveSettings();
  } catch (error) {
    els.settingsStatus.textContent = error.message;
  }
});

els.testModel.addEventListener("click", async () => {
  try {
    await testSettings();
  } catch (error) {
    els.settingsStatus.textContent = error.message;
  }
});

document.querySelectorAll("[data-example]").forEach((button) => {
  button.addEventListener("click", () => {
    els.intentInput.value = button.dataset.example;
    els.intentInput.focus();
  });
});

els.promptFilter.addEventListener("change", renderPromptLibrary);
els.promptSearch.addEventListener("input", renderPromptLibrary);

window.addEventListener("resize", () => {
  if (currentState) {
    renderTopology(
      currentState.active_result?.nodes || currentState.nodes,
      currentState.active_result?.links || currentState.links,
      currentState.active_result?.policy?.selected_links || [],
    );
  }
});

loadSettings().catch(() => {
  els.settingsStatus.textContent = "配置状态读取失败";
});
renderPromptLibrary();
refresh();
