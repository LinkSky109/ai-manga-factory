from collections.abc import Iterable


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _format_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    parts = [f'{key}="{_escape_label(value)}"' for key, value in labels.items()]
    return "{" + ",".join(parts) + "}"


def _append_metric(lines: list[str], name: str, value: float | int, labels: dict[str, str] | None = None) -> None:
    label_text = _format_labels(labels or {})
    lines.append(f"{name}{label_text} {value}")


def _write_definitions(lines: list[str], definitions: Iterable[tuple[str, str, str]]) -> None:
    for name, metric_type, help_text in definitions:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {metric_type}")


def render_prometheus_metrics(overview: dict) -> str:
    lines: list[str] = []
    _write_definitions(
        lines,
        [
            ("ai_manga_factory_provider_consumed", "gauge", "Provider cumulative consumed units."),
            ("ai_manga_factory_provider_budget_threshold", "gauge", "Provider configured budget threshold."),
            ("ai_manga_factory_provider_alert_active", "gauge", "Whether a provider currently has an active budget alert."),
            ("ai_manga_factory_worker_up", "gauge", "Worker health as a binary availability signal."),
            ("ai_manga_factory_worker_seconds_since_seen", "gauge", "Seconds since the worker last sent a heartbeat."),
            ("ai_manga_factory_job_runs_total", "gauge", "Aggregated job count by status."),
            ("ai_manga_factory_active_alerts_total", "gauge", "Number of active alerts."),
            ("ai_manga_factory_workers_total", "gauge", "Worker count by health status."),
        ],
    )

    alerts_by_provider = {
        alert.scope_key: alert
        for alert in overview["alerts"]
        if getattr(alert, "scope_type", "") == "provider_budget"
    }

    for item in overview["items"]:
        labels = {
            "provider_key": str(item["provider_key"]),
            "provider_type": str(item["provider_type"]),
            "routing_mode": str(item["routing_mode"]),
            "usage_unit": str(item["usage_unit"]),
        }
        _append_metric(lines, "ai_manga_factory_provider_consumed", float(item["consumed"]), labels)
        _append_metric(lines, "ai_manga_factory_provider_budget_threshold", float(item["budget_threshold"]), labels)
        alert = alerts_by_provider.get(str(item["provider_key"]))
        _append_metric(
            lines,
            "ai_manga_factory_provider_alert_active",
            1 if alert is not None else 0,
            {
                **labels,
                "severity": "none" if alert is None else str(alert.severity),
                "status": "resolved" if alert is None else str(alert.status),
            },
        )

    for worker in overview["workers"]:
        labels = {
            "worker_id": str(worker["worker_id"]),
            "worker_type": str(worker["worker_type"]),
            "status": str(worker["status"]),
            "health_status": str(worker["health_status"]),
        }
        _append_metric(
            lines,
            "ai_manga_factory_worker_up",
            1 if worker["health_status"] == "healthy" else 0,
            labels,
        )
        _append_metric(
            lines,
            "ai_manga_factory_worker_seconds_since_seen",
            float(worker["seconds_since_seen"]),
            labels,
        )

    for status_key in ("queued_jobs", "running_jobs", "failed_jobs", "resumable_jobs", "completed_jobs"):
        metric_status = status_key.removesuffix("_jobs")
        _append_metric(
            lines,
            "ai_manga_factory_job_runs_total",
            int(overview["summary"].get(status_key, 0)),
            {"status": metric_status},
        )

    _append_metric(
        lines,
        "ai_manga_factory_active_alerts_total",
        int(overview["summary"].get("active_alerts", 0)),
    )
    _append_metric(
        lines,
        "ai_manga_factory_workers_total",
        int(overview["summary"].get("healthy_workers", 0)),
        {"health_status": "healthy"},
    )
    _append_metric(
        lines,
        "ai_manga_factory_workers_total",
        int(overview["summary"].get("stale_workers", 0)),
        {"health_status": "stale"},
    )

    lines.append("")
    return "\n".join(lines)
