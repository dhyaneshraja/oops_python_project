"""Unit + scenario tests. Run with:  python -m unittest -v"""
import unittest

from link import Link, TransmitStatus
from main import build_default_topology, main as run_main
from metrics import Metrics
from network import Network
from node import ActionType, Host, Node, Router
from packet import DropReason, Packet, PacketStatus
from simulator import Simulator


def line_network(seed=1, loss=0.0):
    """H1 - R1 - R2 - H2, no alternative path."""
    net = Network(seed)
    net.add_node(Host("H1")); net.add_node(Router("R1"))
    net.add_node(Router("R2")); net.add_node(Host("H2"))
    net.add_link("H1", "R1", delay=1, failure_probability=loss)
    net.add_link("R1", "R2", delay=1, failure_probability=loss)
    net.add_link("R2", "H2", delay=1, failure_probability=loss)
    return net


class PacketTests(unittest.TestCase):
    def test_ids_are_unique_and_increasing(self):
        a, b = Packet("A", "B"), Packet("A", "B")
        self.assertLess(a.sequence_id, b.sequence_id)

    def test_record_hop_updates_path_ttl_delay(self):
        p = Packet("A", "C", ttl=5)
        p.record_hop("B", 2.5)
        self.assertEqual((p.path, p.ttl, p.total_delay, p.hop_count), (["A", "B"], 4, 2.5, 1))

    def test_invalid_ttl_rejected(self):
        with self.assertRaises(ValueError):
            Packet("A", "B", ttl=0)


class LinkTests(unittest.TestCase):
    def test_certain_loss_and_no_loss(self):
        p = Packet("A", "B")
        self.assertEqual(Link("A", "B", failure_probability=1.0).transmit(p).status, TransmitStatus.LOST)
        self.assertTrue(Link("A", "B", failure_probability=0.0).transmit(p).delivered)

    def test_down_link_reports_down(self):
        link = Link("A", "B"); link.fail()
        self.assertEqual(link.transmit(Packet("A", "B")).status, TransmitStatus.DOWN)
        link.restore()
        self.assertTrue(link.is_up)

    def test_delay_includes_transmission_time(self):
        p = Packet("A", "B", payload="x" * 980)           # 1000 bytes total
        result = Link("A", "B", bandwidth=8.0, delay=2.0).transmit(p)   # 1 ms on the wire
        self.assertAlmostEqual(result.delay, 3.0)

    def test_validation(self):
        for kwargs in ({"bandwidth": 0}, {"delay": -1}, {"failure_probability": 1.5}):
            with self.assertRaises(ValueError):
                Link("A", "B", **kwargs)
        with self.assertRaises(ValueError):
            Link("A", "A")


class NodeTests(unittest.TestCase):
    def test_node_is_abstract(self):
        with self.assertRaises(TypeError):
            Node("X")

    def test_buffer_is_bounded_and_fifo(self):
        r = Router("R", buffer_capacity=2)
        p1, p2, p3 = Packet("A", "B"), Packet("A", "B"), Packet("A", "B")
        self.assertTrue(r.queue_packet(p1)); self.assertTrue(r.queue_packet(p2))
        self.assertFalse(r.queue_packet(p3))
        self.assertIs(r.next_packet(), p1)
        self.assertEqual(r.buffer_size, 1)

    def test_routing_table_getter_returns_copy(self):
        r = Router("R"); r.set_routing_table({"B": "C"})
        r.routing_table["B"] = "HACKED"
        self.assertEqual(r.next_hop("B"), "C")

    def test_router_actions(self):
        r = Router("R"); r.set_routing_table({"B": "C"})
        self.assertEqual(r.handle_packet(Packet("A", "B")).next_hop, "C")
        self.assertEqual(r.handle_packet(Packet("A", "Z")).reason, DropReason.NO_ROUTE)
        p = Packet("A", "B"); p.ttl = 0
        self.assertEqual(r.handle_packet(p).reason, DropReason.TTL_EXPIRED)

    def test_host_consumes_or_hands_off(self):
        h = Host("H1"); h.add_neighbor("R1")
        self.assertEqual(h.handle_packet(Packet("H1", "H2")).next_hop, "R1")
        incoming = Packet("H2", "H1")
        self.assertEqual(h.handle_packet(incoming).type, ActionType.DELIVER)
        self.assertEqual(h.received, [incoming])
        self.assertEqual(h.handle_packet(Packet("X", "Y")).type, ActionType.DROP)

    def test_polymorphism_same_call_different_behaviour(self):
        r = Router("R"); r.set_routing_table({"B": "C"})
        h = Host("H"); h.add_neighbor("R")
        p = Packet("H", "B")
        self.assertNotEqual(r.handle_packet(p).next_hop, h.handle_packet(p).next_hop)


class NetworkTests(unittest.TestCase):
    def test_shortest_path_prefers_low_delay(self):
        net = build_default_topology()
        self.assertEqual(net.compute_shortest_path("H1", "H2"), (["H1", "R1", "R2", "H2"], 4))

    def test_failure_triggers_reroute(self):
        net = build_default_topology()
        net.rebuild_routing_tables()
        changes = net.simulate_link_failure("R1", "R2")
        self.assertEqual(net.compute_shortest_path("H1", "H2")[0], ["H1", "R1", "R3", "R2", "H2"])
        self.assertEqual(net.get_node("R1").next_hop("H2"), "R3")
        self.assertIn("R1", changes)

    def test_restore_returns_to_original_path(self):
        net = build_default_topology()
        net.simulate_link_failure("R1", "R2"); net.restore_link("R1", "R2")
        self.assertEqual(net.compute_shortest_path("H1", "H2")[0], ["H1", "R1", "R2", "H2"])

    def test_partition_means_no_path(self):
        net = line_network()
        net.simulate_link_failure("R1", "R2")
        self.assertIsNone(net.compute_shortest_path("H1", "H2"))
        self.assertNotIn("H2", net.get_node("R1").routing_table)

    def test_hosts_are_never_transit_nodes(self):
        net = Network()
        for r in ("R1", "R2"):
            net.add_node(Router(r))
        net.add_node(Host("H"))
        net.add_link("R1", "H", delay=1); net.add_link("H", "R2", delay=1)   # only path is via a host
        self.assertIsNone(net.compute_shortest_path("R1", "R2"))

    def test_errors(self):
        net = line_network()
        with self.assertRaises(KeyError):
            net.compute_shortest_path("H1", "NOPE")
        with self.assertRaises(KeyError):
            net.simulate_link_failure("H1", "H2")
        with self.assertRaises(ValueError):
            net.add_link("H1", "R1")

    def test_dijkstra_on_weighted_graph(self):
        net = Network()
        for r in "ABCD":
            net.add_node(Router(r))
        net.add_link("A", "B", delay=1); net.add_link("B", "D", delay=10)
        net.add_link("A", "C", delay=3); net.add_link("C", "D", delay=3)
        self.assertEqual(net.compute_shortest_path("A", "D"), (["A", "C", "D"], 6))


class SimulatorTests(unittest.TestCase):
    def test_simple_delivery(self):
        net = line_network()
        sim = Simulator(net)
        p = sim.schedule_packet(0, "H1", "H2", "hello")
        sim.run()
        self.assertEqual(p.status, PacketStatus.DELIVERED)
        self.assertEqual(p.path, ["H1", "R1", "R2", "H2"])
        self.assertEqual(net.get_node("H2").received, [p])

    def test_certain_loss_drops_packet(self):
        net = line_network(loss=1.0)
        sim = Simulator(net); p = sim.schedule_packet(0, "H1", "H2")
        sim.run()
        self.assertEqual((p.status, p.drop_reason), (PacketStatus.DROPPED, DropReason.LINK_LOSS))

    def test_no_route_after_partition(self):
        net = line_network()
        sim = Simulator(net)
        sim.schedule_link_failure(0, "R1", "R2")
        p = sim.schedule_packet(1, "H1", "H2")
        sim.run()
        self.assertEqual(p.drop_reason, DropReason.NO_ROUTE)

    def test_in_flight_packet_is_rerouted(self):
        net = build_default_topology(loss=0.0)
        sim = Simulator(net)
        p = sim.schedule_packet(0, "H1", "H2")
        sim.schedule_link_failure(1, "R1", "R2")      # p is sitting at R1 when this happens
        sim.run()
        self.assertEqual(p.status, PacketStatus.DELIVERED)
        self.assertEqual(p.path, ["H1", "R1", "R3", "R2", "H2"])
        self.assertTrue(p.rerouted)

    def test_silent_failure_is_discovered_mid_transmission(self):
        net = build_default_topology(loss=0.0)
        sim = Simulator(net)
        p = sim.schedule_packet(0, "H1", "H2")
        sim.schedule_link_failure(1, "R1", "R2", detect=False)
        sim.run()
        self.assertEqual(p.status, PacketStatus.DELIVERED)
        self.assertEqual(p.reroutes, 1)
        self.assertTrue(any(e.kind == "REROUTE" for e in sim.log))

    def test_silent_failure_with_no_alternative_drops(self):
        net = line_network()
        sim = Simulator(net)
        p = sim.schedule_packet(0, "H1", "H2")
        sim.schedule_link_failure(1, "R1", "R2", detect=False)
        sim.run()
        self.assertEqual(p.status, PacketStatus.DROPPED)
        self.assertEqual(p.drop_reason, DropReason.NO_ROUTE)

    def test_ttl_expiry_on_routing_loop(self):
        net = line_network()
        sim = Simulator(net)
        p = sim.schedule_packet(0, "H1", "H2", ttl=4)
        net.rebuild_routing_tables()
        # corrupt the tables to create a R1 <-> R2 loop (run() would rebuild, so step manually)
        net.get_node("R1").set_routing_table({"H2": "R2"})
        net.get_node("R2").set_routing_table({"H2": "R1"})
        for t in range(12):
            sim._step(t)
        self.assertEqual(p.drop_reason, DropReason.TTL_EXPIRED)

    def test_buffer_overflow_drops(self):
        net = line_network()
        net.get_node("R1")._buffer_capacity = 1
        net.get_node("H1").processing_rate = 50
        sim = Simulator(net)
        pkts = [sim.schedule_packet(0, "H1", "H2") for _ in range(10)]
        sim.run()
        self.assertTrue(any(p.drop_reason == DropReason.BUFFER_FULL for p in pkts))

    def test_unknown_node_rejected(self):
        with self.assertRaises(KeyError):
            Simulator(line_network()).schedule_packet(0, "H1", "NOPE")

    def test_same_seed_is_reproducible(self):
        def outcome(seed):
            Packet.reset_ids()
            net = build_default_topology(seed, loss=0.2)
            sim = Simulator(net)
            for t in range(40):
                sim.schedule_packet(t, "H1", "H2")
            sim.run()
            return [p.status for p in sim.packets]
        self.assertEqual(outcome(5), outcome(5))
        self.assertNotEqual(outcome(5), outcome(6))


class MetricsTests(unittest.TestCase):
    def test_numbers(self):
        a, b, c = Packet("A", "B"), Packet("A", "B"), Packet("A", "B")
        a.record_hop("B", 2.0); a.mark_delivered(1)
        b.record_hop("X", 1.0); b.record_hop("B", 3.0); b.mark_delivered(2)
        c.mark_dropped(DropReason.LINK_LOSS, 1)
        m = Metrics([a, b, c], duration_ticks=2)
        self.assertEqual((m.sent, m.delivered, m.dropped), (3, 2, 1))
        self.assertAlmostEqual(m.delivery_pct, 200 / 3)
        self.assertAlmostEqual(m.loss_pct, 100 / 3)
        self.assertAlmostEqual(m.avg_hops, 1.5)
        self.assertAlmostEqual(m.avg_latency, 3.0)
        self.assertEqual(m.drops_by_reason, {"random link loss": 1})
        self.assertGreater(m.throughput, 0)

    def test_empty_is_safe(self):
        m = Metrics([])
        self.assertEqual((m.delivery_pct, m.avg_hops, m.avg_latency, m.jitter), (0, 0, 0, 0))


class EndToEndTests(unittest.TestCase):
    def test_main_runs_and_reroutes(self):
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()) as out:
            sim = run_main(["--seed", "1"])
        text = out.getvalue()
        self.assertIn("OVERALL METRICS", text)
        self.assertTrue(any(p.rerouted for p in sim.packets))


if __name__ == "__main__":
    unittest.main()
