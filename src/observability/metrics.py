"""Thread-safe Prometheus-compatible metrics registry and exposition formatter."""

from collections import defaultdict
import threading
import time
from typing import Any, Dict, List, Optional, Tuple


class MetricsCollector:
    """Thread-safe in-memory metrics registry formatted for Prometheus scraping."""

    def __init__(self):
        self._lock = threading.Lock()
        # Counters: (metric_name, tuple_sorted_labels) -> float
        self._counters: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = defaultdict(float)
        # Gauges: (metric_name, tuple_sorted_labels) -> float
        self._gauges: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = {}
        # Histograms: (metric_name, tuple_sorted_labels) -> list of float observations
        self._histograms: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], List[float]] = defaultdict(list)

        # Standard metric help descriptions
        self._metric_help = {
            "rag_requests_total": "Total number of HTTP requests processed by the RAG system.",
            "rag_cache_hits_total": "Total number of semantic and exact cache hits by tier.",
            "rag_policy_rejections_total": "Total number of queries rejected by PolicyGuard.",
            "rag_abstentions_total": "Total number of queries where LLM scientifically abstained.",
            "rag_active_requests": "Current number of in-flight active requests.",
            "rag_request_duration_seconds": "End-to-end HTTP request latency in seconds.",
            "rag_retrieval_duration_seconds": "5-way hybrid retrieval execution latency in seconds.",
            "rag_llm_ttft_seconds": "Time to first token (TTFT) for streaming responses in seconds.",
        }

    def _normalize_labels(self, labels: Optional[Dict[str, str]]) -> Tuple[Tuple[str, str], ...]:
        if not labels:
            return ()
        return tuple(sorted((k, str(v)) for k, v in labels.items()))

    def increment_counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Increments a monotonic counter by value."""
        norm_labels = self._normalize_labels(labels)
        with self._lock:
            self._counters[(name, norm_labels)] += value

    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Sets an instantaneous gauge metric value."""
        norm_labels = self._normalize_labels(labels)
        with self._lock:
            self._gauges[(name, norm_labels)] = value

    def record_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Records an observed duration or value in a histogram."""
        norm_labels = self._normalize_labels(labels)
        with self._lock:
            self._histograms[(name, norm_labels)].append(value)

    def get_counter_value(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Retrieves current counter value for testing or internal inspection."""
        norm_labels = self._normalize_labels(labels)
        with self._lock:
            return self._counters.get((name, norm_labels), 0.0)

    def get_gauge_value(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[float]:
        """Retrieves current gauge value."""
        norm_labels = self._normalize_labels(labels)
        with self._lock:
            return self._gauges.get((name, norm_labels))

    def generate_prometheus_exposition(self) -> str:
        """Renders all registered metrics into Prometheus 0.0.4 text format."""
        lines: List[str] = []

        with self._lock:
            # 1. Export Counters
            counter_groups: Dict[str, List[Tuple[Tuple[Tuple[str, str], ...], float]]] = defaultdict(list)
            for (name, labels), val in self._counters.items():
                counter_groups[name].append((labels, val))

            for name, items in sorted(counter_groups.items()):
                help_text = self._metric_help.get(name, f"Counter metric {name}")
                lines.append(f"# HELP {name} {help_text}")
                lines.append(f"# TYPE {name} counter")
                for labels, val in items:
                    lbl_str = self._format_label_string(labels)
                    lines.append(f"{name}{lbl_str} {val}")

            # 2. Export Gauges
            gauge_groups: Dict[str, List[Tuple[Tuple[Tuple[str, str], ...], float]]] = defaultdict(list)
            for (name, labels), val in self._gauges.items():
                gauge_groups[name].append((labels, val))

            for name, items in sorted(gauge_groups.items()):
                help_text = self._metric_help.get(name, f"Gauge metric {name}")
                lines.append(f"# HELP {name} {help_text}")
                lines.append(f"# TYPE {name} gauge")
                for labels, val in items:
                    lbl_str = self._format_label_string(labels)
                    lines.append(f"{name}{lbl_str} {val}")

            # 3. Export Histograms
            hist_groups: Dict[str, List[Tuple[Tuple[Tuple[str, str], ...], List[float]]]] = defaultdict(list)
            for (name, labels), values in self._histograms.items():
                hist_groups[name].append((labels, values))


            for name, items in sorted(hist_groups.items()):
                help_text = self._metric_help.get(name, f"Histogram metric {name}")
                lines.append(f"# HELP {name} {help_text}")
                lines.append(f"# TYPE {name} histogram")

                buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]

                for labels, obs_values in items:
                    lbl_dict = dict(labels)
                    obs_count = len(obs_values)
                    obs_sum = sum(obs_values)

                    for b in buckets:
                        b_count = sum(1 for v in obs_values if v <= b)
                        b_labels = tuple(sorted({**lbl_dict, "le": str(b)}.items()))
                        lines.append(f"{name}_bucket{self._format_label_string(b_labels)} {b_count}")

                    inf_labels = tuple(sorted({**lbl_dict, "le": "+Inf"}.items()))
                    lines.append(f"{name}_bucket{self._format_label_string(inf_labels)} {obs_count}")
                    lines.append(f"{name}_sum{self._format_label_string(labels)} {round(obs_sum, 6)}")
                    lines.append(f"{name}_count{self._format_label_string(labels)} {obs_count}")

        lines.append("")
        return "\n".join(lines)

    def _format_label_string(self, labels: Tuple[Tuple[str, str], ...]) -> str:
        if not labels:
            return ""
        items = [f'{k}="{v}"' for k, v in labels]
        return "{" + ",".join(items) + "}"


# Global singleton metrics collector
metrics_collector = MetricsCollector()
