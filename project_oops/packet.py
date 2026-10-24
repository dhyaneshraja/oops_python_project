# packet.py - the Packet class (one unit of data travelling through the network)

class Packet:
    count = 0                      # static (class) member: packets created so far

    # constructor with default values (this is how Python "overloads" a constructor)
    def __init__(self, source, destination, payload="Hello", ttl=10):
        Packet.count += 1
        self.sequence_id = Packet.count     # public
        self.source = source
        self.destination = destination
        self.payload = payload
        self._path = [source]               # protected (single underscore): nodes visited
        self.__ttl = ttl                    # private (double underscore)
        self.__status = "IN TRANSIT"        # private
        self.drop_reason = ""
        self.delay = 0.0                    # total delay in ms
        self.rerouted = False

    @staticmethod
    def reset_counter():
        Packet.count = 0

    # ---- methods that give controlled access to the private data ----
    def get_ttl(self):
        return self.__ttl

    def get_status(self):
        return self.__status

    def get_path(self):
        return list(self._path)             # a copy, so outside code can't change it

    def hop_count(self):
        return len(self._path) - 1

    def size(self):
        return len(self.payload)            # size in bytes

    def add_hop(self, node_id, delay):
        self._path.append(node_id)
        self.delay += delay
        self.__ttl -= 1

    def add_delay(self, delay):
        self.delay += delay

    def mark_delivered(self):
        self.__status = "DELIVERED"

    def mark_dropped(self, reason):
        self.__status = "DROPPED"
        self.drop_reason = reason

    def is_delivered(self):
        return self.__status == "DELIVERED"

    def is_dropped(self):
        return self.__status == "DROPPED"

    def __str__(self):                      # operator overloading: used by print()
        route = " -> ".join(self._path)
        text = "#" + str(self.sequence_id) + "  " + route + "  "
        if self.is_delivered():
            text += "DELIVERED (" + str(round(self.delay, 2)) + " ms, " + str(self.hop_count()) + " hops)"
        elif self.is_dropped():
            text += "DROPPED (" + self.drop_reason + ")"
        else:
            text += "IN TRANSIT"
        if self.rerouted:
            text += " [rerouted]"
        return text
