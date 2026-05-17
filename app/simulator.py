from __future__ import annotations

from dataclasses import dataclass

from .models import BusinessIntent, Link, NetworkPolicy, Node, SimulationAction, TelemetrySnapshot, VerificationResult


@dataclass(frozen=True)
class CandidatePath:
    nodes: list[str]
    links: list[str]


class NetworkSimulator:
    def __init__(self) -> None:
        self.nodes = [
            Node(id="beijing-campus", label="北京园区", domain="华北接入域", kind="campus"),
            Node(id="tianjin-core", label="天津骨干", domain="华北骨干域", kind="backbone"),
            Node(id="jinan-core", label="济南骨干", domain="华东骨干域", kind="backbone"),
            Node(id="shanghai-cloud", label="上海云服务", domain="华东云域", kind="cloud"),
            Node(id="guangzhou-dr", label="广州灾备", domain="华南灾备域", kind="dr"),
        ]
        self.links: dict[str, Link] = {
            "lnk-beijing-tianjin": Link(
                id="lnk-beijing-tianjin",
                source="beijing-campus",
                target="tianjin-core",
                domain="华北接入域",
                latency_ms=8,
                loss_percent=0.1,
                capacity_mbps=1000,
                utilization_percent=38,
            ),
            "lnk-tianjin-jinan": Link(
                id="lnk-tianjin-jinan",
                source="tianjin-core",
                target="jinan-core",
                domain="跨域骨干",
                latency_ms=18,
                loss_percent=0.2,
                capacity_mbps=800,
                utilization_percent=46,
            ),
            "lnk-jinan-shanghai": Link(
                id="lnk-jinan-shanghai",
                source="jinan-core",
                target="shanghai-cloud",
                domain="华东云域",
                latency_ms=15,
                loss_percent=0.2,
                capacity_mbps=1000,
                utilization_percent=42,
            ),
            "lnk-tianjin-guangzhou": Link(
                id="lnk-tianjin-guangzhou",
                source="tianjin-core",
                target="guangzhou-dr",
                domain="南向备份域",
                latency_ms=20,
                loss_percent=0.3,
                capacity_mbps=600,
                utilization_percent=35,
            ),
            "lnk-guangzhou-shanghai": Link(
                id="lnk-guangzhou-shanghai",
                source="guangzhou-dr",
                target="shanghai-cloud",
                domain="华南云互联",
                latency_ms=17,
                loss_percent=0.2,
                capacity_mbps=700,
                utilization_percent=33,
            ),
        }
        self.candidate_paths = [
            CandidatePath(
                nodes=["beijing-campus", "tianjin-core", "jinan-core", "shanghai-cloud"],
                links=["lnk-beijing-tianjin", "lnk-tianjin-jinan", "lnk-jinan-shanghai"],
            ),
            CandidatePath(
                nodes=["beijing-campus", "tianjin-core", "guangzhou-dr", "shanghai-cloud"],
                links=["lnk-beijing-tianjin", "lnk-tianjin-guangzhou", "lnk-guangzhou-shanghai"],
            ),
        ]

    def topology(self) -> tuple[list[Node], list[Link]]:
        return self.nodes, list(self.links.values())

    def telemetry(self) -> list[TelemetrySnapshot]:
        snapshots: list[TelemetrySnapshot] = []
        for link in self.links.values():
            snapshots.append(
                TelemetrySnapshot(
                    link_id=link.id,
                    latency_ms=link.latency_ms,
                    loss_percent=link.loss_percent,
                    utilization_percent=link.utilization_percent,
                    health=link.health,
                )
            )
        return snapshots

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
        return link

    def generate_policy(self, intent: BusinessIntent, avoid_degraded: bool = True) -> NetworkPolicy:
        path = self._select_path(intent, avoid_degraded)
        qos_class = "EF-REALTIME" if intent.service in {"视频会议", "语音", "实时业务"} else "AF-BUSINESS"
        selected_labels = [self._node_label(node_id) for node_id in path.nodes]
        acl_rules = [
            f"permit service={intent.service} src={intent.source} dst={intent.destination}",
            "deny anomalous-flow confidence>0.85",
        ]
        route_rules = [
            f"prefer path {' -> '.join(selected_labels)}",
            "enable fast-reroute on degraded telemetry",
        ]
        config_preview = [
            f"policy id auto intent service {intent.service}",
            f"qos class {qos_class} reserve {intent.min_bandwidth_mbps}mbps",
            f"route intent-path {'/'.join(path.nodes)}",
            "telemetry verify latency loss utilization interval 5s",
        ]
        return NetworkPolicy(
            path=selected_labels,
            selected_links=path.links,
            qos_class=qos_class,
            bandwidth_reservation_mbps=intent.min_bandwidth_mbps,
            acl_rules=acl_rules,
            route_rules=route_rules,
            config_preview=config_preview,
        )

    def verify(self, intent: BusinessIntent, policy: NetworkPolicy) -> VerificationResult:
        selected = [self.links[link_id] for link_id in policy.selected_links]
        failed = [link.id for link in selected if link.health == "failed"]
        congested = [link.id for link in selected if link.health == "congested" or link.utilization_percent >= 90]
        latency = sum(link.latency_ms for link in selected)
        loss = round(sum(link.loss_percent for link in selected), 2)
        bottleneck = max(link.utilization_percent for link in selected)

        issues: list[str] = []
        if failed:
            issues.append(f"路径包含故障链路: {', '.join(failed)}")
        if congested:
            issues.append(f"路径包含拥塞链路: {', '.join(congested)}")
        if latency > intent.max_latency_ms:
            issues.append(f"端到端时延 {latency}ms 超过 SLA {intent.max_latency_ms}ms")
        if loss > intent.max_loss_percent:
            issues.append(f"端到端丢包率 {loss}% 超过 SLA {intent.max_loss_percent}%")

        passed = not issues
        return VerificationResult(
            status="achieved" if passed else "partial",
            passed=passed,
            latency_ms=latency,
            loss_percent=loss,
            bottleneck_utilization_percent=bottleneck,
            issues=issues,
            recommendation="策略满足当前业务意图。" if passed else "建议触发 Healing Agent 重新规划避障路径。",
        )

    def _select_path(self, intent: BusinessIntent, avoid_degraded: bool) -> CandidatePath:
        scored: list[tuple[int, CandidatePath]] = []
        for candidate in self.candidate_paths:
            links = [self.links[link_id] for link_id in candidate.links]
            latency = sum(link.latency_ms for link in links)
            loss = sum(link.loss_percent for link in links)
            utilization = max(link.utilization_percent for link in links)
            degraded_penalty = sum(200 for link in links if link.health == "failed")
            congested_penalty = sum(80 for link in links if link.health == "congested" or link.utilization_percent >= 90)
            sla_penalty = 0
            if latency > intent.max_latency_ms:
                sla_penalty += 40
            if loss > intent.max_loss_percent:
                sla_penalty += 40
            score = latency + int(loss * 20) + utilization // 4 + sla_penalty
            if avoid_degraded:
                score += degraded_penalty + congested_penalty
            scored.append((score, candidate))
        return min(scored, key=lambda item: item[0])[1]

    def _node_label(self, node_id: str) -> str:
        return next(node.label for node in self.nodes if node.id == node_id)

    def _baseline(self, link_id: str) -> Link:
        baseline = {
            "lnk-beijing-tianjin": Link(id=link_id, source="beijing-campus", target="tianjin-core", domain="华北接入域", latency_ms=8, loss_percent=0.1, capacity_mbps=1000, utilization_percent=38),
            "lnk-tianjin-jinan": Link(id=link_id, source="tianjin-core", target="jinan-core", domain="跨域骨干", latency_ms=18, loss_percent=0.2, capacity_mbps=800, utilization_percent=46),
            "lnk-jinan-shanghai": Link(id=link_id, source="jinan-core", target="shanghai-cloud", domain="华东云域", latency_ms=15, loss_percent=0.2, capacity_mbps=1000, utilization_percent=42),
            "lnk-tianjin-guangzhou": Link(id=link_id, source="tianjin-core", target="guangzhou-dr", domain="南向备份域", latency_ms=20, loss_percent=0.3, capacity_mbps=600, utilization_percent=35),
            "lnk-guangzhou-shanghai": Link(id=link_id, source="guangzhou-dr", target="shanghai-cloud", domain="华南云互联", latency_ms=17, loss_percent=0.2, capacity_mbps=700, utilization_percent=33),
        }
        return baseline[link_id]
