"""main.py - wires everything together and runs the demo scenario.

Usage:
    python main.py                      # default demo
    python main.py --verbose            # print every event as it happens
    python main.py --plot               # also save results/netsim_results.png
    python main.py --silent-failure     # routers only discover the failure when a send fails
    python main.py --seed 7 --packets 40 --fail-tick 12 --restore-tick -1
"""
import argparse
import os

from metrics import Metrics
from network import Network
from node import Host, Router
from packet import Packet
from simulator import Simulator

FAILED_LINK = ("R1", "R2")
MAIN_FLOW = ("H1", "H2")

POSITIONS = {"H1": (0, 1), "R1": (1, 1), "R2": (3, 1), "H2": (4, 1),
             "R3": (2, -0.1), "H3": (2, -1.1)}


def build_default_topology(seed=None, loss=0.03):
    """The topology from the project schematic (plus a spare host H3):

        H1 --- R1 ------- R2 --- H2
                 \\       /
                  \\-R3--/
                     |
                     H3
    """
    net = Network(seed=seed)
    for r in ("R1", "R2", "R3"):
        net.add_node(Router(r))
    for h in ("H1", "H2", "H3"):
        net.add_node(Host(h))
    net.add_link("H1", "R1", bandwidth=100, delay=1, failure_probability=loss)
    net.add_link("R1", "R2", bandwidth=50, delay=2, failure_probability=loss)   # fast primary
    net.add_link("R1", "R3", bandwidth=20, delay=3, failure_probability=loss)   # slower detour
    net.add_link("R3", "R2", bandwidth=20, delay=3, failure_probability=loss)
    net.add_link("R2", "H2", bandwidth=100, delay=1, failure_probability=loss)
    net.add_link("R3", "H3", bandwidth=100, delay=1, failure_probability=loss)
    return net


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="NetSim - packet routing simulator")
    p.add_argument("--seed", type=int, default=42, help="random seed (default 42)")
    p.add_argument("--packets", type=int, default=30, help="packets in the main H1->H2 flow")
    p.add_argument("--fail-tick", type=int, default=10, help="tick at which R1-R2 fails")
    p.add_argument("--restore-tick", type=int, default=20,
                   help="tick at which R1-R2 is restored (-1 = never)")
    p.add_argument("--loss", type=float, default=0.03, help="per-link random loss probability")
    p.add_argument("--payload", type=int, default=500, help="payload bytes per packet")
    p.add_argument("--silent-failure", action="store_true",
                   help="link failure is undetected until a packet tries to use it")
    p.add_argument("--verbose", action="store_true", help="print every simulation event")
    p.add_argument("--plot", action="store_true", help="save graphs (needs matplotlib)")
    p.add_argument("--out", default="results", help="output folder for graphs")
    return p.parse_args(argv)


def phase_of(tick, fail_tick, restore_tick):
    if tick < fail_tick:
        return "BEFORE failure"
    if restore_tick is None or tick < restore_tick:
        return "DURING failure"
    return "AFTER restore"


def main(argv=None):
    args = parse_args(argv)
    restore_tick = args.restore_tick if args.restore_tick >= 0 else None
    if restore_tick is not None and restore_tick <= args.fail_tick:
        raise SystemExit("--restore-tick must be later than --fail-tick")

    Packet.reset_ids()
    net = build_default_topology(args.seed, args.loss)
    sim = Simulator(net, verbose=args.verbose)

    # traffic: main flow H1->H2 every tick, plus a reverse flow H2->H1 every 2 ticks
    payload = "x" * args.payload
    for t in range(args.packets):
        sim.schedule_packet(t, "H1", "H2", payload)
        if t % 2 == 0:
            sim.schedule_packet(t, "H2", "H1", payload)
    sim.schedule_link_failure(args.fail_tick, *FAILED_LINK, detect=not args.silent_failure)
    if restore_tick is not None:
        sim.schedule_link_restore(restore_tick, *FAILED_LINK)

    print("=" * 72)
    print(" NetSim - packet routing and delivery with OOP")
    print("=" * 72)
    print("Topology (cost = link delay in ms):")
    for link in net.links:
        print(f"  {link}")
    before = net.compute_shortest_path(*MAIN_FLOW)
    print(f"\nShortest path {MAIN_FLOW[0]}->{MAIN_FLOW[1]} (healthy): "
          f"{' -> '.join(before[0])}  (cost {before[1]:g} ms)")
    print(f"Scenario: link {FAILED_LINK[0]}-{FAILED_LINK[1]} fails at tick {args.fail_tick}"
          + (f", restored at tick {restore_tick}" if restore_tick is not None else ", never restored")
          + (" [silent failure]" if args.silent_failure else "") + "\n")

    if args.verbose:
        print("---- live event log ----")
    sim.run()

    if not args.verbose:
        print("---- key events (failures, route updates, reroutes, drops) ----")
        for e in sim.log:
            if e.kind in ("LINKDOWN", "LINKUP", "ROUTES", "REROUTE", "DROP", "WARNING"):
                print(" ", e)

    print("\n---- packet journeys ----")
    for p in sim.packets:
        print(f"  {p.journey()}   ({phase_of(p.created_tick, args.fail_tick, restore_tick)})")

    duration = sim.tick + 1
    overall = Metrics(sim.packets, duration)
    print()
    print(overall.report("OVERALL METRICS (all flows)"))
    for name in ("BEFORE failure", "DURING failure", "AFTER restore"):
        subset = overall.subset(lambda p, n=name: (p.source, p.destination) == MAIN_FLOW
                                and phase_of(p.created_tick, args.fail_tick, restore_tick) == n)
        if subset.sent:
            print()
            print(subset.report(f"{MAIN_FLOW[0]}->{MAIN_FLOW[1]} {name}"))

    if args.plot:
        from plots import make_results_figure
        os.makedirs(args.out, exist_ok=True)
        # compute the two paths the plot highlights without disturbing the finished run
        ref = build_default_topology(args.seed, args.loss)
        path_before = ref.compute_shortest_path(*MAIN_FLOW)[0]
        ref.simulate_link_failure(*FAILED_LINK)
        path_after = ref.compute_shortest_path(*MAIN_FLOW)[0]
        fig = make_results_figure(ref, POSITIONS, sim.packets, MAIN_FLOW, args.fail_tick,
                                  restore_tick, FAILED_LINK, path_before, path_after,
                                  os.path.join(args.out, "netsim_results.png"))
        print(f"\nGraph saved to {fig}")
    return sim


if __name__ == "__main__":
    main()
