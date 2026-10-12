"""network.py - the topology (graph of nodes + links) and ALL routing logic.

Network HAS nodes and links (composition). It is the only module that runs
Dijkstra and (re)builds routing tables; routers just look results up.
"""
import heapq
import random

from link import Link
from node import Host, Router


class Network:
    def __init__(self, seed=None):
        self._seed = seed
        self._nodes = {}                  # id -> Node
        self._adjacency = {}              # id -> {neighbour id -> Link}  (adjacency list)

    # -- building the topology --------------------------------------------
    def add_node(self, node):
        if node.node_id in self._nodes:
            raise ValueError(f"duplicate node id {node.node_id}")
        self._nodes[node.node_id] = node
        self._adjacency[node.node_id] = {}
        return node

    def add_link(self, a, b, bandwidth=10.0, delay=1.0, failure_probability=0.0):
        for n in (a, b):
            if n not in self._nodes:
                raise KeyError(f"unknown node {n}")
        if b in self._adjacency[a]:
            raise ValueError(f"link {a}-{b} already exists")
        # each link gets its own reproducible RNG stream derived from the seed
        rng = random.Random(f"{self._seed}:{'-'.join(sorted((a, b)))}")
        link = Link(a, b, bandwidth, delay, failure_probability, rng)
        self._adjacency[a][b] = link
        self._adjacency[b][a] = link
        self._nodes[a].add_neighbor(b)
        self._nodes[b].add_neighbor(a)
        return link

    # -- lookups -----------------------------------------------------------
    def get_node(self, node_id):
        return self._nodes[node_id]

    def get_link(self, a, b):
        return self._adjacency.get(a, {}).get(b)

    @property
    def nodes(self):
        return [self._nodes[k] for k in sorted(self._nodes)]

    @property
    def routers(self):
        return [n for n in self.nodes if isinstance(n, Router)]

    @property
    def hosts(self):
        return [n for n in self.nodes if isinstance(n, Host)]

    @property
    def links(self):
        seen, out = set(), []
        for a in sorted(self._adjacency):
            for b, link in sorted(self._adjacency[a].items()):
                key = frozenset((a, b))
                if key not in seen:
                    seen.add(key)
                    out.append(link)
        return out

    # -- Dijkstra ----------------------------------------------------------
    def _dijkstra(self, source):
        """Single-source shortest paths over links that are currently UP.

        Packets are never routed *through* a node with forwards_traffic False
        (i.e. a Host), only to or from it.
        """
        dist = {source: 0.0}
        prev = {}
        heap = [(0.0, source)]
        done = set()
        while heap:
            d, u = heapq.heappop(heap)
            if u in done:
                continue
            done.add(u)
            if u != source and not self._nodes[u].forwards_traffic:
                continue
            for v, link in sorted(self._adjacency[u].items()):
                if not link.is_up:
                    continue
                nd = d + link.cost
                if nd < dist.get(v, float("inf")):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(heap, (nd, v))
        return dist, prev

    def compute_shortest_path(self, source, destination):
        """Return (path, cost) for the cheapest route, or None if unreachable."""
        for n in (source, destination):
            if n not in self._nodes:
                raise KeyError(f"unknown node {n}")
        dist, prev = self._dijkstra(source)
        if destination not in dist:
            return None
        path = [destination]
        while path[-1] != source:
            path.append(prev[path[-1]])
        path.reverse()
        return path, dist[destination]

    # -- routing tables ----------------------------------------------------
    def routing_snapshot(self):
        return {r.node_id: r.routing_table for r in self.routers}

    def rebuild_routing_tables(self):
        """Recompute every router's table. Returns what changed:
        {router_id: {destination: (old_next_hop, new_next_hop)}}."""
        changes = {}
        for router in self.routers:
            old = router.routing_table
            dist, prev = self._dijkstra(router.node_id)
            new = {}
            for dest in dist:
                if dest == router.node_id:
                    continue
                hop = dest
                while prev[hop] != router.node_id:
                    hop = prev[hop]
                new[dest] = hop
            router.set_routing_table(new)
            diff = {d: (old.get(d), new.get(d))
                    for d in set(old) | set(new) if old.get(d) != new.get(d)}
            if diff:
                changes[router.node_id] = dict(sorted(diff.items()))
        return changes

    # -- failures ----------------------------------------------------------
    def _require_link(self, a, b):
        link = self.get_link(a, b)
        if link is None:
            raise KeyError(f"no link between {a} and {b}")
        return link

    def simulate_link_failure(self, a, b, reroute=True):
        """Take a link down. With reroute=True the network recalculates at once;
        with reroute=False routers only find out when a transmission fails."""
        self._require_link(a, b).fail()
        return self.rebuild_routing_tables() if reroute else {}

    def restore_link(self, a, b, reroute=True):
        self._require_link(a, b).restore()
        return self.rebuild_routing_tables() if reroute else {}
