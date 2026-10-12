"""simulator.py - owns the clock; walks packets hop by hop and logs everything.

It contains NO routing logic: it asks each node what to do (polymorphism) and
follows the answer.
"""
from collections import defaultdict
from dataclasses import dataclass

from link import TransmitStatus
from node import ActionType
from packet import DropReason, Packet, PacketStatus


@dataclass(frozen=True)
class LogEvent:
    tick: int
    kind: str
    node: str
    packet_id: int
    detail: str

    def __str__(self):
        pid = f"#{self.packet_id}" if self.packet_id is not None else "-"
        return f"[t={self.tick:03d}] {self.kind:<8} {pid:<4} @{self.node:<3} {self.detail}"


class Simulator:
    def __init__(self, network, max_ticks=10_000, verbose=False, output=print):
        self.network = network
        self.max_ticks = max_ticks
        self.verbose = verbose
        self._output = output
        self._packets = []
        self._injections = defaultdict(list)    # tick -> [Packet]
        self._events = defaultdict(list)        # tick -> [callable(tick)]
        self._log = []
        self.tick = 0

    # -- scenario set-up ---------------------------------------------------
    def schedule_packet(self, tick, source, destination, payload="", ttl=Packet.DEFAULT_TTL):
        for n in (source, destination):
            self.network.get_node(n)             # raises KeyError if unknown
        packet = Packet(source, destination, payload, ttl, created_tick=tick)
        self._packets.append(packet)
        self._injections[tick].append(packet)
        return packet

    def schedule_link_failure(self, tick, a, b, detect=True):
        """detect=False: routers only discover the failure when a send fails."""
        def event(t):
            changes = self.network.simulate_link_failure(a, b, reroute=detect)
            self._emit(t, "LINKDOWN", a, None, f"link {a}-{b} FAILED"
                       + ("" if detect else " (undetected until used)"))
            self._log_route_changes(t, changes)
        self._events[tick].append(event)

    def schedule_link_restore(self, tick, a, b):
        def event(t):
            changes = self.network.restore_link(a, b)
            self._emit(t, "LINKUP", a, None, f"link {a}-{b} RESTORED")
            self._log_route_changes(t, changes)
        self._events[tick].append(event)

    # -- results -----------------------------------------------------------
    @property
    def packets(self):
        return list(self._packets)

    @property
    def log(self):
        return list(self._log)

    def log_for(self, packet_id):
        return [e for e in self._log if e.packet_id == packet_id]

    # -- main loop ---------------------------------------------------------
    def run(self):
        """Run until all scheduled work is done and the network is idle."""
        self.network.rebuild_routing_tables()
        last = max([*self._injections, *self._events, 0])
        t = 0
        while t <= self.max_ticks:
            self.tick = t
            self._step(t)
            if t >= last and not self._busy():
                break
            t += 1
        else:
            self._emit(t, "WARNING", "-", None, "max_ticks reached; stopping")
        return self.packets

    def _busy(self):
        return any(n.has_packets for n in self.network.nodes)

    def _step(self, tick):
        for event in self._events.pop(tick, []):
            event(tick)

        for packet in self._injections.pop(tick, []):
            planned = self.network.compute_shortest_path(packet.source, packet.destination)
            packet.planned_path = planned[0] if planned else None
            self.network.get_node(packet.source).send(packet)
            self._emit(tick, "CREATED", packet.source, packet.sequence_id,
                       f"to {packet.destination} ({packet.size_bytes} B, ttl={packet.ttl})")

        for host in self.network.hosts:
            for packet in host.flush_send_queue():
                self._drop(packet, host.node_id, DropReason.BUFFER_FULL, tick)

        arrivals = []                                    # packets landing next tick
        for node in self.network.nodes:
            for _ in range(node.processing_rate):
                packet = node.next_packet()
                if packet is None:
                    break
                self._process(node, packet, tick, arrivals)

        for node_id, packet in arrivals:
            if not self.network.get_node(node_id).queue_packet(packet):
                self._drop(packet, node_id, DropReason.BUFFER_FULL, tick)

    # -- per-packet handling ----------------------------------------------
    def _process(self, node, packet, tick, arrivals):
        action = node.handle_packet(packet)              # polymorphic call
        self._act(node, packet, action, tick, arrivals, allow_retry=True)

    def _act(self, node, packet, action, tick, arrivals, allow_retry):
        if action.type is ActionType.DELIVER:
            packet.mark_delivered(tick)
            self._emit(tick, "DELIVER", node.node_id, packet.sequence_id,
                       f"arrived after {packet.total_delay:.2f} ms via "
                       f"{' -> '.join(packet.path)}")
        elif action.type is ActionType.DROP:
            self._drop(packet, node.node_id, action.reason, tick)
        else:
            self._forward(node, packet, action.next_hop, tick, arrivals, allow_retry)

    def _forward(self, node, packet, next_hop, tick, arrivals, allow_retry):
        link = self.network.get_link(node.node_id, next_hop)
        if link is None:
            self._drop(packet, node.node_id, DropReason.NO_ROUTE, tick)
            return
        result = link.transmit(packet)

        if result.status is TransmitStatus.DOWN:
            if not allow_retry:
                self._drop(packet, node.node_id, DropReason.LINK_DOWN, tick)
                return
            # failure discovered mid-transmission: recalculate and try again
            packet.reroutes += 1
            self._emit(tick, "REROUTE", node.node_id, packet.sequence_id,
                       f"link {node.node_id}-{next_hop} is down; recomputing routes")
            self._log_route_changes(tick, self.network.rebuild_routing_tables())
            self._act(node, packet, node.handle_packet(packet), tick, arrivals,
                      allow_retry=False)
        elif result.status is TransmitStatus.LOST:
            self._drop(packet, node.node_id, DropReason.LINK_LOSS, tick,
                       f"lost on link {node.node_id}-{next_hop}")
        else:
            packet.record_hop(next_hop, result.delay)
            arrivals.append((next_hop, packet))
            self._emit(tick, "FORWARD", node.node_id, packet.sequence_id,
                       f"-> {next_hop} ({result.delay:.2f} ms)")

    def _drop(self, packet, node_id, reason, tick, detail=None):
        packet.mark_dropped(reason, tick)
        self._emit(tick, "DROP", node_id, packet.sequence_id, detail or reason.value)

    # -- logging -----------------------------------------------------------
    def _log_route_changes(self, tick, changes):
        for router, diff in changes.items():
            text = ", ".join(f"{d}: {old or '-'}->{new or '-'}" for d, (old, new) in diff.items())
            self._emit(tick, "ROUTES", router, None, text)

    def _emit(self, tick, kind, node, packet_id, detail):
        event = LogEvent(tick, kind, node, packet_id, detail)
        self._log.append(event)
        if self.verbose:
            self._output(str(event))
