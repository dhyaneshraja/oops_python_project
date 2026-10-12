"""node.py - Node (abstract base), Router and Host.

Router and Host never reference each other; the simulator talks to both
through the common Node interface (polymorphism).
"""
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from enum import Enum

from packet import DropReason


class ActionType(Enum):
    FORWARD = "forward"
    DELIVER = "deliver"
    DROP = "drop"


@dataclass(frozen=True)
class Action:
    """A node's decision about what to do with a packet."""
    type: ActionType
    next_hop: str = None
    reason: DropReason = None

    @staticmethod
    def forward(next_hop):
        return Action(ActionType.FORWARD, next_hop=next_hop)

    @staticmethod
    def deliver():
        return Action(ActionType.DELIVER)

    @staticmethod
    def drop(reason):
        return Action(ActionType.DROP, reason=reason)


class Node(ABC):
    """Abstract network node: id, neighbours and an encapsulated packet buffer."""

    forwards_traffic = True   # may other nodes' packets be routed *through* this node?

    def __init__(self, node_id, buffer_capacity=32, processing_rate=2):
        if buffer_capacity <= 0 or processing_rate <= 0:
            raise ValueError("buffer_capacity and processing_rate must be positive")
        self.node_id = node_id
        self._neighbors = set()
        self._buffer = deque()                # private: use the methods below
        self._buffer_capacity = buffer_capacity
        self.processing_rate = processing_rate   # packets handled per tick

    # -- neighbours --------------------------------------------------------
    @property
    def neighbors(self):
        return sorted(self._neighbors)

    def add_neighbor(self, node_id):
        self._neighbors.add(node_id)

    # -- buffer (encapsulated) --------------------------------------------
    def queue_packet(self, packet):
        """Store a packet. Returns False (and stores nothing) if the buffer is full."""
        if len(self._buffer) >= self._buffer_capacity:
            return False
        self._buffer.append(packet)
        return True

    def next_packet(self):
        """Remove and return the oldest buffered packet, or None."""
        return self._buffer.popleft() if self._buffer else None

    @property
    def buffer_size(self):
        return len(self._buffer)

    @property
    def has_packets(self):
        return bool(self._buffer)

    # -- behaviour every node MUST define differently ----------------------
    @abstractmethod
    def handle_packet(self, packet):
        """Decide what to do with a packet; return an Action."""

    def __repr__(self):
        return f"{type(self).__name__}({self.node_id})"


class Router(Node):
    """Forwards packets using a routing table computed by Network."""

    def __init__(self, node_id, **kwargs):
        super().__init__(node_id, **kwargs)
        self._routing_table = {}      # destination id -> next-hop id

    @property
    def routing_table(self):
        return dict(self._routing_table)      # copy: callers can't mutate ours

    def set_routing_table(self, table):
        self._routing_table = dict(table)

    def next_hop(self, destination):
        return self._routing_table.get(destination)

    def handle_packet(self, packet):
        if packet.destination == self.node_id:
            return Action.deliver()
        if packet.ttl <= 0:
            return Action.drop(DropReason.TTL_EXPIRED)
        hop = self.next_hop(packet.destination)
        if hop is None:
            return Action.drop(DropReason.NO_ROUTE)
        return Action.forward(hop)


class Host(Node):
    """End system: originates packets and consumes those addressed to it."""

    forwards_traffic = False      # a host is never a transit node

    def __init__(self, node_id, **kwargs):
        kwargs.setdefault("processing_rate", 4)
        super().__init__(node_id, **kwargs)
        self._send_queue = deque()
        self._received = []

    @property
    def gateway(self):
        """The router this host hands outgoing packets to (first neighbour)."""
        return self.neighbors[0] if self._neighbors else None

    @property
    def received(self):
        return list(self._received)

    def send(self, packet):
        self._send_queue.append(packet)

    def flush_send_queue(self):
        """Move queued outgoing packets into the buffer; return those that didn't fit."""
        rejected = []
        while self._send_queue:
            packet = self._send_queue.popleft()
            if not self.queue_packet(packet):
                rejected.append(packet)
        return rejected

    def handle_packet(self, packet):
        if packet.destination == self.node_id:
            self._received.append(packet)
            return Action.deliver()                 # consume it
        if packet.source == self.node_id and self.gateway is not None:
            return Action.forward(self.gateway)     # hand it off
        return Action.drop(DropReason.NO_ROUTE)     # hosts don't relay others' traffic
