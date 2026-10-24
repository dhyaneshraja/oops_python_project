# node.py - Node (abstract base class), Router and Host
from abc import ABC, abstractmethod
from typing import final


class Node(ABC):
    total_nodes = 0                 # static member: how many nodes exist
    BUFFER_SIZE = 5                 # static member: buffer capacity

    def __init__(self, node_id):
        self.node_id = node_id
        self._neighbors = []        # protected
        self.__buffer = []          # private: only touched through methods
        Node.total_nodes += 1

    @final                          # "final": subclasses must not override this
    def get_id(self):
        return self.node_id

    def add_neighbor(self, other_id):
        if other_id not in self._neighbors:
            self._neighbors.append(other_id)

    def get_neighbors(self):
        return list(self._neighbors)

    # ---- encapsulated buffer ----
    def queue_packet(self, packet):
        if len(self.__buffer) >= Node.BUFFER_SIZE:
            return False            # buffer full
        self.__buffer.append(packet)
        return True

    def get_packet(self):
        if len(self.__buffer) == 0:
            return None
        return self.__buffer.pop(0)

    # ---- methods that subclasses may override ----
    def can_forward(self):
        return True                 # can packets travel THROUGH this node?

    def get_routing_table(self):
        return {}

    def set_routing_table(self, table):
        pass                        # only routers keep a routing table

    # ---- abstract method: every subclass MUST define it ----
    @abstractmethod
    def handle_packet(self, packet):
        """Return a tuple: ('deliver', None), ('forward', next_hop) or ('drop', reason)."""

    def __str__(self):
        return type(self).__name__ + " " + self.node_id


class Router(Node):
    def __init__(self, node_id):
        super().__init__(node_id)           # call the parent constructor
        self.__routing_table = {}           # destination -> next hop

    def get_routing_table(self):            # overrides Node.get_routing_table
        return dict(self.__routing_table)

    def set_routing_table(self, table):     # overrides Node.set_routing_table
        self.__routing_table = dict(table)

    def handle_packet(self, packet):        # overrides the abstract method
        if packet.destination == self.node_id:
            return ("deliver", None)
        if packet.get_ttl() <= 0:
            return ("drop", "TTL expired")
        if packet.destination not in self.__routing_table:
            return ("drop", "no route to destination")
        return ("forward", self.__routing_table[packet.destination])


class Host(Node):
    def __init__(self, node_id):
        super().__init__(node_id)
        self.received = []                  # packets that arrived here

    def can_forward(self):                  # overrides Node.can_forward
        return False                        # a host is never a "middle" node

    def handle_packet(self, packet):        # overrides the abstract method
        if packet.destination == self.node_id:
            self.received.append(packet)
            return ("deliver", None)
        if packet.source == self.node_id and len(self._neighbors) > 0:
            return ("forward", self._neighbors[0])   # hand to my router (gateway)
        return ("drop", "host cannot forward")
