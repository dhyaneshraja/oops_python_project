"""packet.py - the Packet class: one unit of data moving through the network."""
import itertools
from enum import Enum


class PacketStatus(Enum):
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    DROPPED = "DROPPED"


class DropReason(Enum):
    LINK_LOSS = "random link loss"
    LINK_DOWN = "link down"
    NO_ROUTE = "no route to destination"
    TTL_EXPIRED = "TTL expired"
    BUFFER_FULL = "buffer full"


class Packet:
    """A packet with an auto-generated unique id, a TTL and the hop path it took."""

    HEADER_BYTES = 20
    DEFAULT_TTL = 16
    _id_counter = itertools.count(1)

    def __init__(self, source, destination, payload="", ttl=DEFAULT_TTL, created_tick=0):
        if ttl <= 0:
            raise ValueError("TTL must be positive")
        self.sequence_id = next(Packet._id_counter)
        self.source = source
        self.destination = destination
        self.payload = payload
        self.ttl = ttl
        self.created_tick = created_tick
        self.finished_tick = None
        self.path = [source]            # every node visited, in order
        self.total_delay = 0.0          # ms: propagation + transmission delay
        self.reroutes = 0               # times a failed link forced a re-lookup
        self.planned_path = None        # route the network planned when it was sent
        self.status = PacketStatus.IN_TRANSIT
        self.drop_reason = None

    @classmethod
    def reset_ids(cls):
        """Restart the id counter (used for reproducible demo output and tests)."""
        cls._id_counter = itertools.count(1)

    @property
    def size_bytes(self):
        return self.HEADER_BYTES + len(self.payload.encode("utf-8"))

    @property
    def hop_count(self):
        return len(self.path) - 1

    @property
    def current_node(self):
        return self.path[-1]

    @property
    def rerouted(self):
        """True if the packet was re-routed in flight (forced retry, or it ended up
        on a different path than the one planned when it was sent)."""
        if self.reroutes:
            return True
        return (self.status is PacketStatus.DELIVERED and self.planned_path is not None
                and self.path != self.planned_path)

    def record_hop(self, node_id, delay):
        """Record a successful link traversal; costs one TTL."""
        self.path.append(node_id)
        self.total_delay += delay
        self.ttl -= 1

    def mark_delivered(self, tick):
        self.status = PacketStatus.DELIVERED
        self.finished_tick = tick

    def mark_dropped(self, reason, tick):
        self.status = PacketStatus.DROPPED
        self.drop_reason = reason
        self.finished_tick = tick

    def journey(self):
        """One-line, human-readable trace of this packet's life."""
        route = " -> ".join(self.path)
        if self.status is PacketStatus.DELIVERED:
            tail = f"DELIVERED  {self.total_delay:6.2f} ms  {self.hop_count} hops"
        elif self.status is PacketStatus.DROPPED:
            tail = f"DROPPED at {self.current_node} ({self.drop_reason.value})"
        else:
            tail = "IN TRANSIT"
        extra = "  [rerouted in flight]" if self.rerouted else ""
        return f"#{self.sequence_id:<3} {route:<28} {tail}{extra}"

    def __repr__(self):
        return (f"Packet(#{self.sequence_id} {self.source}->{self.destination}, "
                f"ttl={self.ttl}, {self.status.value})")
