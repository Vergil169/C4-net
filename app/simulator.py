from __future__ import annotations

from dataclasses import dataclass

from .models import BusinessIntent, HealingTraceStep, Link, NetworkPolicy, Node, SimulationAction, TelemetrySnapshot, VerificationResult
from .utils import persist_runtime_state, restore_simulator_state


@dataclass(frozen=True)
class CandidatePath:
    nodes: list[str]
    links: list[str]
    role: str = "normal"


MAX_HEALING_RETRIES = 3


class NetworkSimulator:
    def __init__(self) -> None:
        self.nodes = [
            Node(id="beijing-campus", label="北京园区", domain="华北接入域", kind="campus"),
            Node(id="tianjin-core", label="天津骨干", domain="华北骨干域", kind="backbone"),
            Node(id="jinan-core", label="济南骨干", domain="华东骨干域", kind="backbone"),
            Node(id="shanghai-cloud", label="上海云服务", domain="华东云域", kind="cloud"),
            Node(id="guangzhou-dr", label="广州灾备", domain="华南灾备域", kind="dr"),
            Node(id="nanjing-edge", label="南京边缘", domain="低时延备份域", kind="edge"),
        ]
        self.links: dict[str, Link] = {
            "lnk-beijing-tianjin": Link(id="lnk-beijing-tianjin", source="beijing-campus", target="tianjin-core", domain="华北接入域", latency_ms=8, loss_percent=0.1, capacity_mbps=1000, utilization_percent=38),
            "lnk-tianjin-jinan": Link(id="lnk-tianjin-jinan", source="tianjin-core", target="jinan-core", domain="跨域骨干", latency_ms=18, loss_percent=0.2, capacity_mbps=800, utilization_percent=46),
            "lnk-jinan-shanghai": Link(id="lnk-jinan-shanghai", source="jinan-core", target="shanghai-cloud", domain="华东云域", latency_ms=15, loss_percent=0.2, capacity_mbps=1000, utilization_percent=42),
            "lnk-beijing-shanghai-private": Link(id="lnk-beijing-shanghai-private", source="beijing-campus", target="shanghai-cloud", domain="低时延专线", link_type="low_latency_dedicated", latency_ms=25, loss_percent=0.05, capacity_mbps=200, utilization_percent=26),
            "lnk-tianjin-guangzhou": Link(id="lnk-tianjin-guangzhou", source="tianjin-core", target="guangzhou-dr", domain="南向备份域", latency_ms=20, loss_percent=0.3, capacity_mbps=600, utilization_percent=35),
            "lnk-guangzhou-shanghai": Link(id="lnk-guangzhou-shanghai", source="guangzhou-dr", target="shanghai-cloud", domain="华南云互联", latency_ms=17, loss_percent=0.2, capacity_mbps=700, utilization_percent=33),
            "lnk-tianjin-nanjing": Link(id="lnk-tianjin-nanjing", source="tianjin-core", target="nanjing-edge", domain="低时延备份域", latency_ms=12, loss_percent=0.1, capacity_mbps=900, utilization_percent=28),
            "lnk-nanjing-shanghai": Link(id="lnk-nanjing-shanghai", source="nanjing-edge", target="shanghai-cloud", domain="低时延备份域", latency_ms=10, loss_percent=0.1, capacity_mbps=900, utilization_percent=31),
        }
        self.candidate_paths = [
            CandidatePath(nodes=["beijing-campus", "tianjin-core", "jinan-core", "shanghai-cloud"], links=["lnk-beijing-tianjin", "lnk-tianjin-jinan", "lnk-jinan-shanghai"], role="current"),
            CandidatePath(nodes=["beijing-campus", "shanghai-cloud"], links=["lnk-beijing-shanghai-private"], role="dedicated"),
            CandidatePath(nodes=["beijing-campus", "tianjin-core", "guangzhou-dr", "shanghai-cloud"], links=["lnk-beijing-tianjin", "lnk-tianjin-guangzhou", "lnk-guangzhou-shanghai"], role="transit"),
            CandidatePath(nodes=["beijing-campus", "tianjin-core", "nanjing-edge", "shanghai-cloud"], links=["lnk-beijing-tianjin", "lnk-tianjin-nanjing", "lnk-nanjing-shanghai"], role="backup"),
        ]
        restore_simulator_state(self)

    def topology(self) -> tuple[list[Node], list[Link]]:
        return self.nodes, list(self.links.values())

    def telemetry(self) -> list[TelemetrySnapshot]:
        return [
            TelemetrySnapshot(link_id=link.id, latency_ms=link.latency_ms, loss_percent=link.loss_percent, utilization_percent=link.utilization_percent, health=link.health)
            for link in self.links.values()
        ]

    def apply_simulation(self, action: SimulationAction, link_id: str) -> Link:
        link = self.links[link_id]
        if action == "congest":
            link.health = "congested"
            link.utilization_percent = 94
            link.latency_ms = max(link.latency_ms, 42)
            link.loss_percent = max(link.loss_percent, 1.8)
        elif action == "fail":
            link.health = "failed"
            link.utilization_percent = 100
            link.latency_ms = max(link.latency_ms, 999)
            link.loss_percent = 100.0
        else:
            baseline = self._baseline(link_id)
            link.health = "normal"
            link.utilization_percent = baseline.utilization_percent
            link.latency_ms = baseline.latency_ms
            link.loss_percent = baseline.loss_percent
        persist_runtime_state(self)
        return link

    def generate_policy(self, intent: BusinessIntent, avoid_degraded: bool = True) -> NetworkPolicy:
        return self._policy_from_candidate(intent, self._select_path(intent, avoid_degraded, prefer_current=True))

    def heal_policy(self, intent: BusinessIntent, max_retries: int = MAX_HEALING_RETRIES) -> tuple[NetworkPolicy, VerificationResult, int]:
        attempts = 0
        policy: NetworkPolicy | None = None
        verification: VerificationResult | None = None
        for attempts in range(1, max_retries + 1):
            candidate = self._select_path(intent, avoid_degraded=True, prefer_current=False)
            policy = self._policy_from_candidate(intent, candidate)
            verification = self.verify(intent, policy)
            if verification.passed:
                break
        assert policy is not None
        assert verification is not None
        if not verification.passed:
            verification.status = "failed"
            verification.severity = "critical"
            verification.issues.append(f"Healing Agent retried {attempts} times; no feasible path available")
            verification.recommendation = "无可行路径，请恢复链路或放宽 SLA 后重新触发自愈。"
        return policy, verification, attempts

    def verify(self, intent: BusinessIntent, policy: NetworkPolicy) -> VerificationResult:
        selected = [self.links[link_id] for link_id in policy.selected_links]
        failed = [link.id for link in selected if link.health == "failed"]
        congested = [link.id for link in selected if link.health == "congested" or link.utilization_percent >= 90]
        latency = sum(link.latency_ms for link in selected)
        loss = round(sum(link.loss_percent for link in selected), 2)
        bottleneck = max(link.utilization_percent for link in selected)
        bottleneck_capacity = min(link.capacity_mbps for link in selected)
        feasible_paths = [candidate for candidate in self.candidate_paths if self._path_is_feasible(candidate, intent)]

        issues: list[str] = []
        if not feasible_paths:
            issues.append("No feasible candidate path satisfies health, SLA, and bandwidth constraints")
        if failed:
            issues.append(f"路径包含故障链路: {', '.join(failed)}")
        if congested:
            issues.append(f"路径包含拥塞链路: {', '.join(congested)}")
        if bottleneck_capacity < intent.min_bandwidth_mbps:
            issues.append(f"Insufficient path bandwidth: bottleneck {bottleneck_capacity}Mbps below requested {intent.min_bandwidth_mbps}Mbps")
        if latency > intent.max_latency_ms:
            issues.append(f"端到端时延 {latency}ms 超过 SLA {intent.max_latency_ms}ms")
        if loss > intent.max_loss_percent:
            issues.append(f"端到端丢包率 {loss}% 超过 SLA {intent.max_loss_percent}%")

        passed = not issues
        margin = {
            "latency_ms": float(intent.max_latency_ms - latency),
            "loss_percent": round(float(intent.max_loss_percent - loss), 2),
            "bandwidth_mbps": float(bottleneck_capacity - intent.min_bandwidth_mbps),
        }
        severity = "normal" if passed else "critical"
        if passed and (0 <= margin["latency_ms"] <= 2 or 0 <= margin["loss_percent"] <= 0.2):
            severity = "warning"
        recommendation = "策略满足当前业务意图。"
        if severity == "warning":
            recommendation = "自愈完成，指标接近 SLA 阈值，持续监控链路状态。"
        if not passed:
            recommendation = "建议触发 Healing Agent 重新规划避障路径。"
        status = "achieved" if passed else "failed" if failed or not feasible_paths else "partial"
        return VerificationResult(
            status=status,
            passed=passed,
            latency_ms=latency,
            loss_percent=loss,
            bottleneck_utilization_percent=bottleneck,
            issues=issues,
            recommendation=recommendation,
            severity=severity,
            sla_margin=margin,
        )

    def build_healing_trace(
        self,
        intent: BusinessIntent,
        original_policy: NetworkPolicy,
        original_verification: VerificationResult,
        healed_policy: NetworkPolicy,
        healed_verification: VerificationResult,
        attempts: int,
    ) -> list[HealingTraceStep]:
        original_path = " -> ".join(original_policy.path)
        healed_path = " -> ".join(healed_policy.path)
        failed = not healed_verification.passed
        return [
            HealingTraceStep(stage=1, name="检测告警", status="done", detail=f"检测到链路 SLA 不达标，端到端时延 {original_verification.latency_ms}ms，触发自愈流程", metrics={"latency_ms": original_verification.latency_ms, "threshold_ms": intent.max_latency_ms}, links=original_policy.selected_links),
            HealingTraceStep(stage=2, name="拓扑与资源查询", status="done", detail="查询全网拓扑与链路指标，筛选可用备选路径", links=[link.id for link in self.links.values()]),
            HealingTraceStep(stage=3, name="路径重规划", status="done" if not failed else "blocked", detail=(f"已筛选最优路径：{healed_path}，指标符合 SLA" if not failed else f"已重试 {attempts} 次，未找到满足 SLA 的可行路径"), links=healed_policy.selected_links),
            HealingTraceStep(stage=4, name="路径切换", status="done" if not failed else "blocked", detail=(f"原路径 {original_path} 下线为闲置链路，业务切换至 {healed_path}" if not failed else "自愈失败，拓扑保持原有线路不变"), links=healed_policy.selected_links if not failed else original_policy.selected_links),
            HealingTraceStep(stage=5, name="SLA 二次校验", status="done" if not failed else "blocked", detail=(f"新路径校验通过：时延 {healed_verification.latency_ms}ms，丢包率 {healed_verification.loss_percent}%，带宽 {healed_policy.bandwidth_reservation_mbps}Mbps" if not failed else "无可行路径，无法完成二次校验"), metrics={"latency_ms": healed_verification.latency_ms, "loss_percent": healed_verification.loss_percent, "bandwidth_mbps": healed_policy.bandwidth_reservation_mbps}, links=healed_policy.selected_links),
            HealingTraceStep(stage=6, name="自愈完成", status="done" if not failed else "blocked", detail=(healed_verification.recommendation if not failed else "自愈失败：无可行路径，请恢复链路或放宽 SLA"), metrics={"severity": healed_verification.severity}, links=healed_policy.selected_links),
        ]

    def _policy_from_candidate(self, intent: BusinessIntent, path: CandidatePath) -> NetworkPolicy:
        qos_class = "EF-REALTIME" if intent.service in {"视频会议", "语音", "实时业务"} else "AF-BUSINESS"
        selected_labels = [self._node_label(node_id) for node_id in path.nodes]
        return NetworkPolicy(
            path=selected_labels,
            selected_links=path.links,
            qos_class=qos_class,
            bandwidth_reservation_mbps=intent.min_bandwidth_mbps,
            acl_rules=[
                f"permit service={intent.service} src={intent.source} dst={intent.destination}",
                "deny anomalous-flow confidence>0.85",
            ],
            route_rules=[
                f"prefer path {' -> '.join(selected_labels)}",
                f"path role {path.role}",
                "enable fast-reroute on degraded telemetry",
            ],
            config_preview=[
                f"policy id auto intent service {intent.service}",
                f"qos class {qos_class} reserve {intent.min_bandwidth_mbps}mbps",
                f"route intent-path {'/'.join(path.nodes)}",
                f"route selected-links {','.join(path.links)}",
                "telemetry verify latency loss utilization interval 5s",
            ],
        )

    def _select_path(self, intent: BusinessIntent, avoid_degraded: bool, prefer_current: bool = False) -> CandidatePath:
        primary_path = self.candidate_paths[0]
        if prefer_current:
            return primary_path

        scored: list[tuple[int, CandidatePath]] = []
        for candidate in self.candidate_paths[1:]:
            links = [self.links[link_id] for link_id in candidate.links]
            latency = sum(link.latency_ms for link in links)
            loss = sum(link.loss_percent for link in links)
            utilization = max(link.utilization_percent for link in links)
            bottleneck_capacity = min(link.capacity_mbps for link in links)
            degraded_penalty = sum(200 for link in links if link.health == "failed")
            congested_penalty = sum(80 for link in links if link.health == "congested" or link.utilization_percent >= 90)
            sla_penalty = 0
            if latency > intent.max_latency_ms:
                sla_penalty += 40
            if loss > intent.max_loss_percent:
                sla_penalty += 40
            if bottleneck_capacity < intent.min_bandwidth_mbps:
                sla_penalty += 120 + (intent.min_bandwidth_mbps - bottleneck_capacity) // 10
            score = latency + int(loss * 20) + utilization // 4 + sla_penalty
            if avoid_degraded:
                score += degraded_penalty + congested_penalty
            scored.append((score, candidate))
        return min(scored, key=lambda item: item[0])[1]

    def _path_is_feasible(self, candidate: CandidatePath, intent: BusinessIntent) -> bool:
        links = [self.links[link_id] for link_id in candidate.links]
        latency = sum(link.latency_ms for link in links)
        loss = sum(link.loss_percent for link in links)
        bottleneck_capacity = min(link.capacity_mbps for link in links)
        return (
            all(link.health == "normal" and link.utilization_percent < 90 for link in links)
            and bottleneck_capacity >= intent.min_bandwidth_mbps
            and latency <= intent.max_latency_ms
            and loss <= intent.max_loss_percent
        )

    def _node_label(self, node_id: str) -> str:
        return next(node.label for node in self.nodes if node.id == node_id)

    def _baseline(self, link_id: str) -> Link:
        baseline = {
            "lnk-beijing-tianjin": Link(id=link_id, source="beijing-campus", target="tianjin-core", domain="华北接入域", latency_ms=8, loss_percent=0.1, capacity_mbps=1000, utilization_percent=38),
            "lnk-tianjin-jinan": Link(id=link_id, source="tianjin-core", target="jinan-core", domain="跨域骨干", latency_ms=18, loss_percent=0.2, capacity_mbps=800, utilization_percent=46),
            "lnk-jinan-shanghai": Link(id=link_id, source="jinan-core", target="shanghai-cloud", domain="华东云域", latency_ms=15, loss_percent=0.2, capacity_mbps=1000, utilization_percent=42),
            "lnk-beijing-shanghai-private": Link(id=link_id, source="beijing-campus", target="shanghai-cloud", domain="低时延专线", link_type="low_latency_dedicated", latency_ms=25, loss_percent=0.05, capacity_mbps=200, utilization_percent=26),
            "lnk-tianjin-guangzhou": Link(id=link_id, source="tianjin-core", target="guangzhou-dr", domain="南向备份域", latency_ms=20, loss_percent=0.3, capacity_mbps=600, utilization_percent=35),
            "lnk-guangzhou-shanghai": Link(id=link_id, source="guangzhou-dr", target="shanghai-cloud", domain="华南云互联", latency_ms=17, loss_percent=0.2, capacity_mbps=700, utilization_percent=33),
            "lnk-tianjin-nanjing": Link(id=link_id, source="tianjin-core", target="nanjing-edge", domain="低时延备份域", latency_ms=12, loss_percent=0.1, capacity_mbps=900, utilization_percent=28),
            "lnk-nanjing-shanghai": Link(id=link_id, source="nanjing-edge", target="shanghai-cloud", domain="低时延备份域", latency_ms=10, loss_percent=0.1, capacity_mbps=900, utilization_percent=31),
        }
        return baseline[link_id]
