"""
Metrics dashboard for the secure inference platform.

Reads from the JSONL metrics sink and displays throughput, latency,
tenant breakdown, queue wait times, and system health. Works without
AWS credentials — suitable for air-gapped environments.

Usage:
    streamlit run src/ai_inference/dashboard.py -- --metrics-file metrics.jsonl

    Or with demo mode:
    mise run demo  (in one terminal)
    streamlit run src/ai_inference/dashboard.py  (in another)
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_metrics(path: Path) -> List[Dict[str, Any]]:
    """Load all metric events from a JSONL file."""
    if not path.exists():
        return []
    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO timestamp."""
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Metric aggregation
# ---------------------------------------------------------------------------


def compute_stats(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute dashboard statistics from raw metric events."""
    stats = {
        "total_requests": 0,
        "completed": 0,
        "failed": 0,
        "avg_duration_ms": 0.0,
        "p95_duration_ms": 0.0,
        "avg_queue_wait_ms": 0.0,
        "requests_per_minute": 0.0,
        "model_breakdown": defaultdict(int),
        "event_type_breakdown": defaultdict(int),
        "durations": [],
        "queue_waits": [],
        "throughput_timeline": [],
        "circuit_breaker_transitions": [],
        "scaling_decisions": [],
        "reconciliation_passes": [],
    }

    accepted_times = []

    for event in events:
        metric = event.get("metric", "")

        if metric == "request_accepted":
            stats["total_requests"] += 1
            stats["model_breakdown"][event.get("model", "unknown")] += 1
            stats["event_type_breakdown"][event.get("event_type", "unknown")] += 1
            accepted_times.append(parse_timestamp(event.get("timestamp", "")))

        elif metric == "inference_completed":
            stats["completed"] += 1
            duration = event.get("duration_ms", 0)
            if duration:
                stats["durations"].append(duration)

        elif metric == "inference_failed":
            stats["failed"] += 1

        elif metric == "queue_wait_time":
            wait = event.get("wait_ms", 0)
            if wait:
                stats["queue_waits"].append(wait)

        elif metric == "circuit_breaker_transition":
            stats["circuit_breaker_transitions"].append(event)

        elif metric == "scaling_decision":
            stats["scaling_decisions"].append(event)

        elif metric == "reconciliation_pass":
            stats["reconciliation_passes"].append(event)

    # Compute averages
    if stats["durations"]:
        stats["avg_duration_ms"] = sum(stats["durations"]) / len(stats["durations"])
        sorted_d = sorted(stats["durations"])
        idx = int(len(sorted_d) * 0.95)
        stats["p95_duration_ms"] = sorted_d[min(idx, len(sorted_d) - 1)]

    if stats["queue_waits"]:
        stats["avg_queue_wait_ms"] = sum(stats["queue_waits"]) / len(stats["queue_waits"])

    # Throughput (requests per minute over last 5 minutes)
    if accepted_times:
        now = datetime.now(timezone.utc)
        recent = [t for t in accepted_times if (now - t).total_seconds() < 300]
        if recent:
            span_seconds = max((now - min(recent)).total_seconds(), 1)
            stats["requests_per_minute"] = len(recent) / (span_seconds / 60)

    # Timeline buckets (per minute)
    if accepted_times:
        accepted_times.sort()
        bucket_size = timedelta(minutes=1)
        current_bucket = accepted_times[0].replace(second=0, microsecond=0)
        count = 0
        for t in accepted_times:
            bucket = t.replace(second=0, microsecond=0)
            if bucket == current_bucket:
                count += 1
            else:
                stats["throughput_timeline"].append({"time": current_bucket.isoformat(), "count": count})
                current_bucket = bucket
                count = 1
        stats["throughput_timeline"].append({"time": current_bucket.isoformat(), "count": count})

    return stats


# ---------------------------------------------------------------------------
# Dashboard UI
# ---------------------------------------------------------------------------


def main():
    st.set_page_config(page_title="Inference Platform Metrics", page_icon="📊", layout="wide")

    st.title("📊 Secure Inference Platform — Metrics Dashboard")
    st.caption("Real-time observability from JSONL metrics sink")

    # Sidebar: file selection
    with st.sidebar:
        st.header("⚙️ Configuration")
        default_path = "metrics.jsonl"
        metrics_path = st.text_input("Metrics file path", value=default_path)
        auto_refresh = st.checkbox("Auto-refresh (5s)", value=False)
        if auto_refresh:
            st.empty()
            import time
            time.sleep(5)
            st.rerun()

    path = Path(metrics_path)
    events = load_metrics(path)

    if not events:
        st.warning(f"No metrics found at `{metrics_path}`. Run the platform with a JSONL sink to generate data.")
        st.code("mise run demo  # generates metrics in demo mode\n\n# Or configure JsonlMetricsSink:\n# sink = JsonlMetricsSink('metrics.jsonl')")
        return

    stats = compute_stats(events)

    # Top-level KPIs
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Requests", stats["total_requests"])
    col2.metric("Completed", stats["completed"])
    col3.metric("Failed", stats["failed"])
    col4.metric("Avg Latency", f"{stats['avg_duration_ms']:.0f}ms")
    col5.metric("Req/min", f"{stats['requests_per_minute']:.1f}")

    st.divider()

    # Two-column layout
    left, right = st.columns(2)

    with left:
        st.subheader("Latency Distribution")
        if stats["durations"]:
            import pandas as pd
            df = pd.DataFrame({"duration_ms": stats["durations"]})
            st.bar_chart(df["duration_ms"].value_counts().sort_index())
            st.caption(f"P95: {stats['p95_duration_ms']:.0f}ms | Avg: {stats['avg_duration_ms']:.0f}ms")
        else:
            st.info("No latency data yet")

        st.subheader("Queue Wait Time")
        if stats["queue_waits"]:
            import pandas as pd
            df = pd.DataFrame({"wait_ms": stats["queue_waits"]})
            st.line_chart(df["wait_ms"])
            st.caption(f"Avg wait: {stats['avg_queue_wait_ms']:.0f}ms")
        else:
            st.info("No queue wait data yet")

    with right:
        st.subheader("Model Breakdown")
        if stats["model_breakdown"]:
            import pandas as pd
            df = pd.DataFrame(
                {"model": list(stats["model_breakdown"].keys()),
                 "requests": list(stats["model_breakdown"].values())}
            )
            st.bar_chart(df.set_index("model"))
        else:
            st.info("No model data yet")

        st.subheader("Event Type Breakdown")
        if stats["event_type_breakdown"]:
            import pandas as pd
            df = pd.DataFrame(
                {"event_type": list(stats["event_type_breakdown"].keys()),
                 "requests": list(stats["event_type_breakdown"].values())}
            )
            st.bar_chart(df.set_index("event_type"))
        else:
            st.info("No event type data yet")

    st.divider()

    # Throughput timeline
    st.subheader("Throughput Over Time")
    if stats["throughput_timeline"]:
        import pandas as pd
        df = pd.DataFrame(stats["throughput_timeline"])
        df["time"] = pd.to_datetime(df["time"])
        st.line_chart(df.set_index("time")["count"])
    else:
        st.info("Not enough data for timeline")

    # System events
    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Circuit Breaker Events")
        if stats["circuit_breaker_transitions"]:
            for t in stats["circuit_breaker_transitions"][-10:]:
                st.text(f"{t.get('timestamp', '')[:19]} | {t.get('from_state')} → {t.get('to_state')}")
        else:
            st.success("No circuit breaker transitions (healthy)")

    with col_b:
        st.subheader("Scaling Decisions")
        if stats["scaling_decisions"]:
            for d in stats["scaling_decisions"][-10:]:
                st.text(f"{d.get('timestamp', '')[:19]} | {d.get('action')} ({d.get('current_workers')}→{d.get('desired_workers')})")
        else:
            st.info("No scaling decisions recorded")

    # Raw event count
    st.divider()
    st.caption(f"Total metric events loaded: {len(events)} from `{metrics_path}`")


if __name__ == "__main__":
    main()
