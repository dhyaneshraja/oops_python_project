# link.py - the Link class: a connection between two nodes.
# This is the only place that decides whether a packet is lost.
import random


class Link:
    # default values for delay, bandwidth and loss
    def __init__(self, node_a, node_b, delay=1, bandwidth=10, loss=0.0):
        if not Link.is_valid_loss(loss):
            raise ValueError("loss must be between 0 and 1")
        self.node_a = node_a
        self.node_b = node_b
        self.delay = delay              # ms
        self.bandwidth = bandwidth      # Mbps
        self.loss = loss                # probability of losing a packet
        self.__up = True                # private: use fail() / restore()

    @staticmethod
    def is_valid_loss(value):
        return 0 <= value <= 1

    def is_up(self):
        return self.__up

    def fail(self):
        self.__up = False

    def restore(self):
        self.__up = True

    def transmit(self, packet):
        """Returns a tuple (status, delay). status is 'ok', 'lost' or 'down'."""
        if not self.__up:
            return ("down", 0)
        # propagation delay + time to put the bits on the wire
        total = self.delay + packet.size() * 8 / (self.bandwidth * 1000)
        if random.random() < self.loss:
            return ("lost", total)
        return ("ok", total)

    def __str__(self):
        state = "UP" if self.__up else "DOWN"
        return (self.node_a + " <-> " + self.node_b + "  delay=" + str(self.delay) +
                "ms  bandwidth=" + str(self.bandwidth) + "Mbps  loss=" + str(self.loss) + "  " + state)
