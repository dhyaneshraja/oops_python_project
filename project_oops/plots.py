"""plots.py - OPTIONAL matplotlib graphs (only imported when --plot is used)."""
import matplotlib
matplotlib.use("Agg")                      # render to file; no display needed
import matplotlib.pyplot as plt

from packet import PacketStatus


def _draw_topology(ax, network, positions, title, failed=(), highlight=()):
    ax.set_title(title, fontsize=11, fontweight="bold")
    hl = {frozenset(p) for p in zip(highlight, highlight[1:])}
    for link in network.links:
        (x1, y1), (x2, y2) = positions[link.node_a], positions[link.node_b]
        key = frozenset(link.endpoints)
        if key in {frozenset(f) for f in failed}:
            style = dict(color="#d62728", linestyle="--", linewidth=2.5)
        elif key in hl:
            style = dict(color="#2ca02c", linewidth=4)
        else:
            style = dict(color="#999999", linewidth=1.5)
        ax.plot([x1, x2], [y1, y2], zorder=1, **style)
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.08, f"{link.delay:g} ms",
                ha="center", fontsize=8, color="#444444")
    for node in network.nodes:
        x, y = positions[node.node_id]
        is_host = not node.forwards_traffic
        ax.scatter([x], [y], s=1300, zorder=2, marker="s" if is_host else "o",
                   color="#cfe8cf" if is_host else "#cfcfe8", edgecolors="#333333")
        ax.text(x, y, node.node_id, ha="center", va="center", fontsize=10, fontweight="bold", zorder=3)
    ax.set_xlim(-0.6, 4.6)
    ax.set_ylim(-1.5, 1.7)
    ax.axis("off")


def make_results_figure(network, positions, packets, flow, fail_tick, restore_tick,
                        failed_link, path_before, path_after, path):
    """4-panel figure: topology before/after the failure, per-packet latency
    and a before/during/after comparison."""
    src, dst = flow
    flow_pkts = sorted((p for p in packets if (p.source, p.destination) == flow),
                       key=lambda p: p.created_tick)
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    fig.suptitle(f"NetSim: routing behaviour before vs. after link failure ({failed_link[0]}-{failed_link[1]})",
                 fontsize=14, fontweight="bold")

    _draw_topology(axes[0][0], network, positions, f"Before failure: {src}->{dst} path", highlight=path_before)
    _draw_topology(axes[0][1], network, positions,
                   f"After failure: {failed_link[0]}-{failed_link[1]} down, traffic rerouted",
                   failed=[failed_link], highlight=path_after)

    ax = axes[1][0]
    ok = [p for p in flow_pkts if p.status is PacketStatus.DELIVERED]
    bad = [p for p in flow_pkts if p.status is PacketStatus.DROPPED]
    ax.plot([p.created_tick for p in ok], [p.total_delay for p in ok], "-o", color="#1f77b4",
            label="delivered")
    ax.scatter([p.created_tick for p in bad], [0] * len(bad), marker="x", color="#d62728",
               s=70, label="dropped", zorder=3)
    ax.axvline(fail_tick, color="#d62728", linestyle="--", label="link fails")
    if restore_tick is not None:
        ax.axvline(restore_tick, color="#2ca02c", linestyle="--", label="link restored")
    ax.set_title(f"Latency of each {src}->{dst} packet")
    ax.set_xlabel("tick when packet was sent")
    ax.set_ylabel("latency (ms)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)

    ax = axes[1][1]
    end = restore_tick if restore_tick is not None else float("inf")
    phases = [("before", lambda p: p.created_tick < fail_tick),
              ("during failure", lambda p: fail_tick <= p.created_tick < end)]
    if restore_tick is not None:
        phases.append(("after restore", lambda p: p.created_tick >= restore_tick))
    labels, hops, lat = [], [], []
    from metrics import Metrics
    for name, pred in phases:
        m = Metrics([p for p in flow_pkts if pred(p)])
        labels.append(f"{name}\n({m.delivery_pct:.0f}% delivered)")
        hops.append(m.avg_hops)
        lat.append(m.avg_latency)
    xs = range(len(labels))
    w = 0.38
    b1 = ax.bar([x - w / 2 for x in xs], hops, w, label="avg hops", color="#8c6bb1")
    ax.set_ylabel("average hop count")
    ax2 = ax.twinx()
    b2 = ax2.bar([x + w / 2 for x in xs], lat, w, label="avg latency (ms)", color="#fd8d3c")
    ax2.set_ylabel("average latency (ms)")
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_title("Routing behaviour by phase")
    ax.legend([b1, b2], ["avg hops", "avg latency (ms)"], fontsize=8, loc="upper left")
    for bar, v in zip(b1, hops):
        ax.text(bar.get_x() + bar.get_width() / 2, v, f"{v:.1f}", ha="center", va="bottom", fontsize=8)
    for bar, v in zip(b2, lat):
        ax2.text(bar.get_x() + bar.get_width() / 2, v, f"{v:.1f}", ha="center", va="bottom", fontsize=8)

    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
