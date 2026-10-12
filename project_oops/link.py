"""link.py - the Link class: a physical connection between two nodes.

This is the ONLY place where "does this packet make it across?" is decided.
"""
import random
from dataclasses import dataclass
from enum import Enum


class TransmitStatus(Enum):
    OK = "ok"
    LOST = "lost"      # random loss on a working link
    DOWN = "down"      # link has failed


@dataclass(frozen=True)
class TransmitResult:
    status: TransmitStatus
    delay: float       # milliseconds spent on the link

    @property
    def delivered(self):
        return self.status is TransmitStatus.OK


class Link:
    """Bidirectional link with bandwidth (Mbps), delay (ms) and a loss probability."""

    def __init__(self, node_a, node_b, bandwidth=10.0, delay=1.0,
                 failure_probability=0.0, rng=None):
        if node_a == node_b:
            raise ValueError("A link must connect two different nodes")
        if bandwidth <= 0:
            raise ValueError("bandwidth must be positive")
        if delay < 0:
            raise ValueError("delay cannot be negative")
        if not 0.0 <= failure_probability <= 1.0:
            raise ValueError("failure_probability must be within [0, 1]")
        self.node_a = node_a
        self.node_b = node_b
        self.bandwidth = bandwidth
        self.delay = delay
        self.failure_probability = failure_probability
        self._rng = rng if rng is not None else random.Random()
        self._up = True

    # -- state -------------------------------------------------------------
    @property
    def is_up(self):
        return self._up

    def fail(self):
        self._up = False

    def restore(self):
        self._up = True

    # -- helpers -----------------------------------------------------------
    @property
    def cost(self):
        """Routing metric used by Dijkstra (propagation delay in ms)."""
        return self.delay

    @property
    def endpoints(self):
        return (self.node_a, self.node_b)

    def other_end(self, node_id):
        if node_id == self.node_a:
            return self.node_b
        if node_id == self.node_b:
            return self.node_a
        raise ValueError(f"{node_id} is not an endpoint of {self}")

    def transmission_time(self, packet):
        """Time (ms) to push the packet's bits onto the wire."""
        return packet.size_bytes * 8 / (self.bandwidth * 1_000_000) * 1000

    # -- core behaviour ----------------------------------------------------
    def transmit(self, packet):
        """Decide whether the packet gets through, and how long that takes."""
        if not self._up:
            return TransmitResult(TransmitStatus.DOWN, 0.0)
        delay = self.delay + self.transmission_time(packet)
        if self._rng.random() < self.failure_probability:
            return TransmitResult(TransmitStatus.LOST, delay)
        return TransmitResult(TransmitStatus.OK, delay)

    def __repr__(self):
        state = "UP" if self._up else "DOWN"
        return (f"Link({self.node_a}<->{self.node_b}, {self.bandwidth}Mbps, "
                f"{self.delay}ms, loss={self.failure_probability:.0%}, {state})")
