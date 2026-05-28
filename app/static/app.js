const nodePositions = {
  "beijing-campus": [8, 42],
  "tianjin-core": [31, 23],
  "jinan-core": [56, 28],
  "shanghai-cloud": [78, 45],
  "guangzhou-dr": [48, 70],
};

let currentState = null;
let deepSeekPromptShown = false;

const els = {
  agents: document.querySelector("#agents"),
  apiKey: document.querySelector("#apiKey"),
  bandwidthSla: document.querySelector("#bandwidthSla"),
  baseUrl: document.querySelector("#baseUrl"),
  closeSettings: document.querySelector("#closeSettings"),
  confidence: document.querySelector("#confidence"),
  healIntent: document.querySelector("#healIntent"),
  intentInput: document.querySelector("#intentInput"),
  intentJson: document.querySelector("#intentJson"),
  latencySla: document.querySelector("#latencySla"),
  messages: document.querySelector("#messages"),
  modelName: document.querySelector("#modelName"),
  openSettings: document.querySelector("#openSettings"),
  parseNote: document.querySelector("#parseNote"),
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
  }
}

function renderResult(result) {
  els.statusPill.textContent = statusText(result.status, result.healed);
  els.intentJson.textContent = JSON.stringify(result.intent, null, 2);
  renderIntentSummary(result.intent);
  renderTasks(result.tasks);
  renderMessages(result.messages);
  renderPolicy(result.policy);
  renderVerification(result.verification);
  renderTopology(result.nodes, result.links, result.policy.selected_links);
  els.selectedPath.textContent = result.policy.path.join(" -> ");
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
      const labelX = (x1 + x2) / 2;
      const labelY = (y1 + y2) / 2;
      return `
        <div class="link ${selected} ${link.health}" style="left:${x1}px; top:${y1}px; width:${length}px; transform:rotate(${angle}deg)"></div>
        <div class="link-label" style="left:${labelX}px; top:${labelY}px">${link.latency_ms}ms / ${link.loss_percent}%</div>
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

async function runAction(label, action) {
  try {
    setBusy(true, label);
    await action();
    await refresh();
  } catch (error) {
    els.statusPill.textContent = "操作失败";
    els.parseNote.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

els.submitIntent.addEventListener("click", async () => {
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
});

els.simulateCongestion.addEventListener("click", async () => {
  await runAction("模拟拥塞中", () => api("/api/simulate", {
    method: "POST",
    body: JSON.stringify({ action: "congest", link_id: "lnk-tianjin-jinan" }),
  }));
});

els.simulateFailure.addEventListener("click", async () => {
  await runAction("模拟故障中", () => api("/api/simulate", {
    method: "POST",
    body: JSON.stringify({ action: "fail", link_id: "lnk-tianjin-jinan" }),
  }));
});

els.recoverLink.addEventListener("click", async () => {
  await runAction("恢复链路中", () => api("/api/simulate", {
    method: "POST",
    body: JSON.stringify({ action: "recover", link_id: "lnk-tianjin-jinan" }),
  }));
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
refresh();
