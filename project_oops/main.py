# main.py - builds the network from a file, shows a menu and runs the simulation
import random

from link import Link
from metrics import Metrics
from network import Network, TopologyError
from node import Host, Router
from packet import Packet
from simulator import Simulator

TOPOLOGY_FILE = "topology.txt"
RESULTS_FILE = "netsim_results.txt"


# ---------------------------------------------------------------- file reading
def load_topology(filename):
    """Reads the topology file and returns a Network. Raises exceptions on bad input."""
    network = Network()
    file = open(filename, "r")
    try:
        line_number = 0
        for line in file:
            line_number += 1
            line = line.strip()
            if line == "" or line.startswith("#"):
                continue
            parts = line.split()
            kind = parts[0].upper()
            if kind == "ROUTER" and len(parts) == 2:
                network.add_node(Router(parts[1]))
            elif kind == "HOST" and len(parts) == 2:
                network.add_node(Host(parts[1]))
            elif kind == "LINK" and len(parts) == 6:
                link = Link(parts[1], parts[2], float(parts[3]), float(parts[4]), float(parts[5]))
                network.add_link(parts[1], parts[2], link)
            else:
                raise TopologyError("line " + str(line_number) + ": cannot understand '" + line + "'")
    finally:
        file.close()                # always runs, even if an error happened
    network.rebuild_routing_tables()
    return network


# ---------------------------------------------------------------- file writing / reading
def save_results(simulator, filename):
    file = open(filename, "w")
    file.write("NETSIM RESULTS\n\n")
    file.write("EVENT LOG\n")
    for line in simulator.log:
        file.write(line + "\n")
    file.write("\nPACKET JOURNEYS\n")
    for p in simulator.packets:
        file.write(str(p) + "\n")
    file.write("\n" + Metrics(simulator.packets).report("OVERALL METRICS"))
    file.close()
    print("Results saved to " + filename)


def show_file(filename):
    try:
        file = open(filename, "r")
        print(file.read())
        file.close()
    except FileNotFoundError:
        print("No saved results yet. Choose option 7 first.")


# ---------------------------------------------------------------- console input helpers
def ask_host(network, message):
    name = input(message).strip().upper()
    node = network.get_node(name)           # may raise TopologyError
    if not isinstance(node, Host):
        raise TopologyError(name + " is not a host")
    return name


def ask_number(message, default):
    text = input(message + " [" + str(default) + "]: ").strip()
    if text == "":
        return default
    return int(text)                        # may raise ValueError


def show_routing_tables(network):
    for node_id in network.nodes:
        table = network.get_node(node_id).get_routing_table()
        if table:
            print("Routing table of " + node_id + ":")
            for destination in sorted(table):
                print("   to " + destination + " via " + table[destination])


def show_links(network):
    for key in network.links:
        print("  " + str(network.links[key]))


# ---------------------------------------------------------------- the automatic demo
def run_demo(simulator, packets_per_phase):
    network = simulator.network
    path = network.compute_shortest_path("H1", "H2")
    print("\nPhase 1: healthy network. Best path H1 -> H2: " + " -> ".join(path[0]) +
          " (cost " + str(path[1]) + " ms)")
    simulator.send("H1", "H2", packets_per_phase)
    phase1 = len(simulator.packets)

    print("\nPhase 2: link R1-R2 fails.")
    simulator.fail_link("R1", "R2")
    simulator.send("H1", "H2", packets_per_phase)
    phase2 = len(simulator.packets)

    print("\nPhase 3: link R1-R2 is restored.")
    simulator.restore_link("R1", "R2")
    simulator.send("H1", "H2", packets_per_phase)

    print("\nPhase 4: link fails WITHOUT routers knowing (found in the middle of a journey).")
    simulator.fail_link("R1", "R2", False)
    simulator.send("H1", "H2", 2)

    print()
    packets = simulator.packets
    print(Metrics(packets[0:phase1]).report("Phase 1 - before failure"))
    print(Metrics(packets[phase1:phase2]).report("Phase 2 - during failure"))
    print(Metrics(packets[phase2:]).report("Phase 3 and 4 - after restore / silent failure"))
    print(Metrics(packets).report("OVERALL"))
    simulator.restore_link("R1", "R2")


# ---------------------------------------------------------------- main menu
def main():
    random.seed(3)                          # same results every run (remove for random runs)
    Packet.reset_counter()
    try:
        network = load_topology(TOPOLOGY_FILE)
    except FileNotFoundError:
        print("Cannot find " + TOPOLOGY_FILE + ". Run this program from the netsim folder.")
        return
    except (ValueError, TopologyError) as error:
        print("Problem in " + TOPOLOGY_FILE + ": " + str(error))
        return

    simulator = Simulator(network)
    print("=== NetSim: Network Packet Simulator ===")
    print("Loaded " + str(len(network.nodes)) + " nodes and " + str(len(network.links)) + " links.")

    while True:
        print("\n1. Run the full automatic demo")
        print("2. Send packets between two hosts")
        print("3. Fail a link")
        print("4. Restore a link")
        print("5. Show routing tables")
        print("6. Show metrics")
        print("7. Save results to file")
        print("8. View saved results file")
        print("9. Show links")
        print("0. Exit")
        choice = input("Enter choice: ").strip()

        try:
            if choice == "1":
                run_demo(simulator, ask_number("Packets per phase", 5))
            elif choice == "2":
                source = ask_host(network, "Source host (H1/H2/H3): ")
                destination = ask_host(network, "Destination host: ")
                simulator.send(source, destination, ask_number("How many packets", 3))
            elif choice == "3":
                a = input("First node of the link: ").strip().upper()
                b = input("Second node of the link: ").strip().upper()
                simulator.fail_link(a, b)
            elif choice == "4":
                a = input("First node of the link: ").strip().upper()
                b = input("Second node of the link: ").strip().upper()
                simulator.restore_link(a, b)
            elif choice == "5":
                show_routing_tables(network)
            elif choice == "6":
                print(Metrics(simulator.packets).report("METRICS SO FAR"))
            elif choice == "7":
                save_results(simulator, RESULTS_FILE)
            elif choice == "8":
                show_file(RESULTS_FILE)
            elif choice == "9":
                show_links(network)
            elif choice == "0":
                print("Goodbye!")
                break
            else:
                print("Please enter a number from 0 to 9.")
        except ValueError:
            print("Error: please type a whole number.")
        except TopologyError as error:
            print("Error: " + str(error))


main()
