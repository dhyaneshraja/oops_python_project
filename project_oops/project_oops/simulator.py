# simulator.py - moves each packet through the network hop by hop and keeps a log
from packet import Packet


class Simulator:
    def __init__(self, network):
        self.network = network
        self.packets = []           # every packet that was sent
        self.log = []               # list of text lines
        self.show_log = True

    def _write(self, text):
        self.log.append(text)
        if self.show_log:
            print("   " + text)

    # count has a default value, so send("H1","H2") sends one packet
    def send(self, source, destination, count=1, payload="x" * 500):
        for i in range(count):
            self.send_packet(Packet(source, destination, payload))

    def fail_link(self, a, b, detect=True):
        changes = self.network.fail_link(a, b, detect)
        self._write("*** LINK " + a + "-" + b + " FAILED" + ("" if detect else " (routers don't know yet)"))
        for line in changes:
            self._write("route update  " + line)

    def restore_link(self, a, b):
        changes = self.network.restore_link(a, b)
        self._write("*** LINK " + a + "-" + b + " RESTORED")
        for line in changes:
            self._write("route update  " + line)

    def send_packet(self, packet):
        self.packets.append(packet)
        self._write("Packet #" + str(packet.sequence_id) + " created: " +
                    packet.source + " -> " + packet.destination)
        current = packet.source
        retried = False
        while True:
            node = self.network.get_node(current)
            if not node.queue_packet(packet):
                packet.mark_dropped("buffer full")
                self._write("Packet #" + str(packet.sequence_id) + " dropped at " + current + " (buffer full)")
                return
            node.get_packet()
            # polymorphism: same call, but Router and Host behave differently
            action, value = node.handle_packet(packet)

            if action == "deliver":
                packet.mark_delivered()
                self._write("Packet #" + str(packet.sequence_id) + " DELIVERED to " + current +
                            " in " + str(round(packet.delay, 2)) + " ms")
                return
            if action == "drop":
                packet.mark_dropped(value)
                self._write("Packet #" + str(packet.sequence_id) + " dropped at " + current + " (" + value + ")")
                return

            # action == "forward": send it over the link to the next hop
            link = self.network.get_link(current, value)
            status, delay = link.transmit(packet)
            if status == "down":
                if retried:
                    packet.mark_dropped("link down")
                    self._write("Packet #" + str(packet.sequence_id) + " dropped at " + current + " (link down)")
                    return
                retried = True
                packet.rerouted = True
                self._write("Packet #" + str(packet.sequence_id) + " found link " + current + "-" +
                            value + " DOWN at " + current + "; recalculating routes")
                for line in self.network.rebuild_routing_tables():
                    self._write("route update  " + line)
                continue            # try again from the same node
            if status == "lost":
                packet.add_delay(delay)
                packet.mark_dropped("lost on link")
                self._write("Packet #" + str(packet.sequence_id) + " LOST on link " + current + "-" + value)
                return
            packet.add_hop(value, delay)
            self._write("Packet #" + str(packet.sequence_id) + " " + current + " -> " + value +
                        " (" + str(round(delay, 2)) + " ms)")
            current = value
            retried = False
