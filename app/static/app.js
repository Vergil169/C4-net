const nodePositions = {
  "beijing-campus": [8, 42],
  "tianjin-core": [31, 23],
  "jinan-core": [56, 28],
  "shanghai-cloud": [78, 45],
  "guangzhou-dr": [48, 70],
};

let currentState = null;

const els = {
  agents: document.querySelector("#agents"),
  healIntent: document.querySelector("#healIntent"),
  intentInput: document.querySelector("#intentInput"),
  intentJson: document.querySelector("#intentJson"),
  messages: document.querySelector("#messages"),
  policy: document.querySelector("#policy"),
  recoverLink: document.querySelector("#recoverLink"),
  selectedPath: document.querySelector("#selectedPath"),
  simulateCongestion: document.querySelector("#simulateCongestion"),
  simulateFailure: document.querySelector("#simulateFailure"),
  statusPill: document.querySelector("#statusPill"),
  submitIntent: document.querySelector("#submitIntent"),
  tasks: document.querySelector("#tasks"),
  telemetry: document.querySelector("#telemetry"),
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
  renderTasks(result.tasks);
  renderMessages(result.messages);
  renderPolicy(result.policy);
  renderVerification(result.verification);
  renderTopology(result.nodes, result.links, result.policy.selected_links);
  els.selectedPath.textContent = result.policy.path.join(" -> ");
}

function renderAgents(agents) {
  els.agents.innerHTML = agents
    .map((agent) => `
      <div class="agent">
        <strong>${agent.name}</strong>
        <span>${agent.role} · ${agent.capabilities.join(" / ")}</span>
      </div>
    `)
    .join("");
}

function renderTasks(tasks) {
  els.tasks.innerHTML = tasks
    .map((task) => `
      <div class="task">
        <strong>${task.id} · ${task.agent}</strong>
        <span>${task.action} · ${task.detail}</span>
      </div>
    `)
    .join("");
}

function renderMessages(messages) {
  els.messages.innerHTML = messages
    .map((message) => `
      <div class="message">
        <strong>${message.sender} -> ${message.receiver}</strong>
        <span>${message.performative} · ${shortPayload(message.payload)}</span>
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
    <div class="policy-block"><strong>${policy.policy_id}</strong><br />${policy.qos_class} · ${policy.bandwidth_reservation_mbps} Mbps</div>
    <div class="policy-block"><strong>路径</strong><br />${policy.path.join(" -> ")}</div>
    <div class="policy-block"><strong>ACL</strong><br />${policy.acl_rules.join("<br />")}</div>
    <div class="policy-block"><strong>配置预览</strong>${policy.config_preview.map((line) => `<code>${line}</code>`).join("")}</div>
  `;
}

function renderVerification(result) {
  if (!result) {
    els.verification.innerHTML = "";
    return;
  }
  const cls = result.passed ? "ok" : "bad";
  els.verification.innerHTML = `
    <div class="metric ${cls}"><span>状态</span><strong>${result.status}</strong></div>
    <div class="metric ${cls}"><span>结果</span><strong>${result.passed ? "通过" : "需自愈"}</strong></div>
    <div class="metric"><span>端到端时延</span><strong>${result.latency_ms}ms</strong></div>
    <div class="metric"><span>丢包率</span><strong>${result.loss_percent}%</strong></div>
    <div class="metric"><span>瓶颈利用率</span><strong>${result.bottleneck_utilization_percent}%</strong></div>
    <div class="metric"><span>建议</span><strong>${result.recommendation}</strong></div>
  `;
}

function renderTelemetry(telemetry) {
  els.telemetry.innerHTML = telemetry
    .map((item) => `
      <div class="metric ${item.health === "normal" ? "ok" : "bad"}">
        <span>${item.link_id}</span>
        <strong>${item.health}</strong>
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
      return `<div class="node" style="left:${x}%; top:${y}%">${node.label}<br /><small>${node.domain}</small></div>`;
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

function shortPayload(payload) {
  const raw = JSON.stringify(payload);
  return raw.length > 96 ? `${raw.slice(0, 96)}...` : raw;
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

els.submitIntent.addEventListener("click", async () => {
  const result = await api("/api/intents", {
    method: "POST",
    body: JSON.stringify({ text: els.intentInput.value }),
  });
  renderResult(result);
  await refresh();
});

els.simulateCongestion.addEventListener("click", async () => {
  await api("/api/simulate", {
    method: "POST",
    body: JSON.stringify({ action: "congest", link_id: "lnk-tianjin-jinan" }),
  });
  await refresh();
});

els.simulateFailure.addEventListener("click", async () => {
  await api("/api/simulate", {
    method: "POST",
    body: JSON.stringify({ action: "fail", link_id: "lnk-tianjin-jinan" }),
  });
  await refresh();
});

els.recoverLink.addEventListener("click", async () => {
  await api("/api/simulate", {
    method: "POST",
    body: JSON.stringify({ action: "recover", link_id: "lnk-tianjin-jinan" }),
  });
  await refresh();
});

els.healIntent.addEventListener("click", async () => {
  const result = await api("/api/heal", { method: "POST" });
  renderResult(result);
  await refresh();
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

refresh();
