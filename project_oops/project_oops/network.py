# network.py - the topology (nodes + links) and ALL routing logic (Dijkstra)


class TopologyError(Exception):
    """Our own exception, raised when the network description is wrong."""


class Network:
    def __init__(self):
        self.nodes = {}             # node_id -> Node object
        self.links = {}             # (id1, id2) -> Link object

    @staticmethod
    def make_key(a, b):
        return tuple(sorted([a, b]))

    def add_node(self, node):
        if node.get_id() in self.nodes:
            raise TopologyError("duplicate node " + node.get_id())
        self.nodes[node.get_id()] = node

    def add_link(self, a, b, link):
        if a not in self.nodes or b not in self.nodes:
            raise TopologyError("link " + a + "-" + b + " uses an unknown node")
        self.links[Network.make_key(a, b)] = link
        self.nodes[a].add_neighbor(b)
        self.nodes[b].add_neighbor(a)

    def get_node(self, node_id):
        if node_id not in self.nodes:
            raise TopologyError("unknown node " + node_id)
        return self.nodes[node_id]

    def get_link(self, a, b):
        return self.links.get(Network.make_key(a, b))

    # ---------------- Dijkstra's algorithm ----------------
    def _dijkstra(self, source):
        distance = {source: 0}      # best known cost to each node
        previous = {}               # previous[x] = node before x on the best path
        visited = []
        while True:
            # pick the unvisited node with the smallest distance
            current = None
            for node_id in distance:
                if node_id not in visited:
                    if current is None or distance[node_id] < distance[current]:
                        current = node_id
            if current is None:
                break
            visited.append(current)
            # packets may start at a host but never pass THROUGH one
            if current != source and not self.nodes[current].can_forward():
                continue
            for neighbor in self.nodes[current].get_neighbors():
                link = self.get_link(current, neighbor)
                if not link.is_up():
                    continue        # failed links are ignored
                new_cost = distance[current] + link.delay
                if neighbor not in distance or new_cost < distance[neighbor]:
                    distance[neighbor] = new_cost
                    previous[neighbor] = current
        return distance, previous

    def compute_shortest_path(self, source, destination):
        """Returns (path_list, cost) or None if there is no path."""
        self.get_node(source)
        self.get_node(destination)
        distance, previous = self._dijkstra(source)
        if destination not in distance:
            return None
        path = [destination]
        while path[-1] != source:
            path.append(previous[path[-1]])     # walk backwards from the destination
        path.reverse()
        return (path, distance[destination])

    # ---------------- routing tables ----------------
    def rebuild_routing_tables(self):
        """Recalculates every router's table. Returns a list of text lines describing changes."""
        changes = []
        for node_id in self.nodes:
            node = self.nodes[node_id]
            if not node.can_forward():
                continue                            # hosts don't keep routing tables
            distance, previous = self._dijkstra(node_id)
            table = {}
            for destination in distance:
                if destination == node_id:
                    continue
                hop = destination                   # walk back to find the first hop
                while previous[hop] != node_id:
                    hop = previous[hop]
                table[destination] = hop
            old = node.get_routing_table()
            node.set_routing_table(table)           # hosts ignore this call
            for destination in table:
                if old.get(destination) != table[destination]:
                    changes.append(node_id + ": to " + destination + " via " +
                                   str(old.get(destination, "-")) + " -> " + table[destination])
            for destination in old:
                if destination not in table:        # route disappeared
                    changes.append(node_id + ": to " + destination + " via " + old[destination] +
                                   " -> UNREACHABLE")
        return changes

    # ---------------- failures ----------------
    def fail_link(self, a, b, detect=True):
        link = self.get_link(a, b)
        if link is None:
            raise TopologyError("no link between " + a + " and " + b)
        link.fail()
        if detect:
            return self.rebuild_routing_tables()
        return []                   # undetected: routers still have old tables

    def restore_link(self, a, b):
        link = self.get_link(a, b)
        if link is None:
            raise TopologyError("no link between " + a + " and " + b)
        link.restore()
        return self.rebuild_routing_tables()
