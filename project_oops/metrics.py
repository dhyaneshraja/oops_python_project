"""metrics.py - reads finished Packet objects and computes performance numbers.

It knows nothing about how packets moved, so new metrics can be added here
without touching the simulation.
"""
import statistics
from collections import Counter

from packet import PacketStatus


class Metrics:
    def __init__(self, packets, duration_ticks=None):
        self.packets = list(packets)
        self.duration_ticks = duration_ticks

    def subset(self, predicate):
        return Metrics([p for p in self.packets if predicate(p)], self.duration_ticks)

    # -- basic counts ------------------------------------------------------
    @property
    def sent(self):
        return len(self.packets)

    @property
    def delivered_packets(self):
        return [p for p in self.packets if p.status is PacketStatus.DELIVERED]

    @property
    def delivered(self):
        return len(self.delivered_packets)

    @property
    def dropped(self):
        return sum(p.status is PacketStatus.DROPPED for p in self.packets)

    # -- ratios ------------------------------------------------------------
    @property
    def delivery_pct(self):
        return 100.0 * self.delivered / self.sent if self.sent else 0.0

    @property
    def loss_pct(self):
        return 100.0 * self.dropped / self.sent if self.sent else 0.0

    # -- path / latency ----------------------------------------------------
    @property
    def avg_hops(self):
        d = self.delivered_packets
        return statistics.mean(p.hop_count for p in d) if d else 0.0

    @property
    def avg_latency(self):
        d = self.delivered_packets
        return statistics.mean(p.total_delay for p in d) if d else 0.0

    @property
    def max_latency(self):
        d = self.delivered_packets
        return max(p.total_delay for p in d) if d else 0.0

    @property
    def jitter(self):
        """Standard deviation of latency among delivered packets."""
        d = self.delivered_packets
        return statistics.pstdev(p.total_delay for p in d) if len(d) > 1 else 0.0

    @property
    def throughput(self):
        """Delivered bytes per simulation tick."""
        if not self.duration_ticks:
            return 0.0
        return sum(p.size_bytes for p in self.delivered_packets) / self.duration_ticks

    @property
    def rerouted(self):
        return sum(1 for p in self.packets if p.rerouted)

    @property
    def drops_by_reason(self):
        return dict(Counter(p.drop_reason.value for p in self.packets
                            if p.status is PacketStatus.DROPPED))

    # -- output ------------------------------------------------------------
    def summary(self):
        return {
            "sent": self.sent, "delivered": self.delivered, "dropped": self.dropped,
            "delivery_pct": self.delivery_pct, "loss_pct": self.loss_pct,
            "avg_hops": self.avg_hops, "avg_latency_ms": self.avg_latency,
            "max_latency_ms": self.max_latency, "jitter_ms": self.jitter,
            "throughput_bytes_per_tick": self.throughput, "rerouted": self.rerouted,
            "drops_by_reason": self.drops_by_reason,
        }

    def report(self, title="Metrics"):
        lines = [f"--- {title} ---",
                 f"  Packets sent / delivered / dropped : {self.sent} / {self.delivered} / {self.dropped}",
                 f"  Delivery %                         : {self.delivery_pct:.1f}",
                 f"  Loss %                             : {self.loss_pct:.1f}",
                 f"  Average hop count                  : {self.avg_hops:.2f}",
                 f"  Average latency (ms)               : {self.avg_latency:.2f}",
                 f"  Jitter (ms, std dev)               : {self.jitter:.2f}",
                 f"  Throughput (bytes/tick)            : {self.throughput:.1f}",
                 f"  Packets rerouted                   : {self.rerouted}"]
        if self.drops_by_reason:
            reasons = ", ".join(f"{k}: {v}" for k, v in self.drops_by_reason.items())
            lines.append(f"  Drop reasons                       : {reasons}")
        return "\n".join(lines)
