"""
Range Rover Sport L494 Multi-Module Diagnostic Tool

Interactive CLI for scanning and clearing DTCs across all vehicle modules
via the OBD2 port using an ELM327 adapter.

Usage:
    python main.py                    # Auto-detect port
    python main.py --port COM3        # Specify port
    python main.py --list-ports       # List available ports
"""

import argparse
import sys
import time

try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init()
except ImportError:
    # Fallback if colorama not installed
    class Fore:
        RED = GREEN = YELLOW = CYAN = MAGENTA = WHITE = RESET = ""
    class Style:
        BRIGHT = RESET_ALL = ""

from elm327 import ELM327, ELM327Error
from modules import MODULES, get_module_by_name, get_all_module_names
from scanner import DiagnosticScanner, ModuleScanResult
from uds import DTC


# --- Display Helpers ---

def print_header():
    """Print application header."""
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"  Range Rover Sport L494 - Diagnostic Scanner")
    print(f"  Multi-Module DTC Reader / Reset Tool")
    print(f"{'='*60}{Style.RESET_ALL}\n")


def print_separator():
    print(f"{Fore.CYAN}{'─'*60}{Style.RESET_ALL}")


def print_success(msg: str):
    print(f"  {Fore.GREEN}✓{Style.RESET_ALL} {msg}")


def print_error(msg: str):
    print(f"  {Fore.RED}✗{Style.RESET_ALL} {msg}")


def print_warning(msg: str):
    print(f"  {Fore.YELLOW}!{Style.RESET_ALL} {msg}")


def print_info(msg: str):
    print(f"  {Fore.CYAN}>{Style.RESET_ALL} {msg}")


def print_dtc(dtc: DTC, index: int):
    """Print a single DTC with color-coded status."""
    status_color = Fore.RED if dtc.is_active else (
        Fore.YELLOW if dtc.is_confirmed else Fore.WHITE
    )
    print(f"    {index}. {Style.BRIGHT}{dtc.code}{Style.RESET_ALL}"
          f"  [{status_color}{dtc.status_text}{Style.RESET_ALL}]"
          f"  (raw: {dtc.raw_bytes.hex().upper()})")


def print_module_result(result: ModuleScanResult):
    """Print scan result for a single module."""
    mod = result.module
    if not result.is_present:
        print(f"  {Fore.WHITE}{mod.short_name:6s}{Style.RESET_ALL}"
              f" {mod.description:40s}"
              f" {Fore.WHITE}[Not responding]{Style.RESET_ALL}")
        return

    if result.error:
        print(f"  {Fore.YELLOW}{mod.short_name:6s}{Style.RESET_ALL}"
              f" {mod.description:40s}"
              f" {Fore.YELLOW}[Error: {result.error}]{Style.RESET_ALL}")
        return

    dtc_count = len(result.dtcs)
    if dtc_count == 0:
        print(f"  {Fore.GREEN}{mod.short_name:6s}{Style.RESET_ALL}"
              f" {mod.description:40s}"
              f" {Fore.GREEN}[No faults]{Style.RESET_ALL}")
    else:
        active = sum(1 for d in result.dtcs if d.is_active)
        print(f"  {Fore.RED}{mod.short_name:6s}{Style.RESET_ALL}"
              f" {mod.description:40s}"
              f" {Fore.RED}[{dtc_count} DTC(s), {active} active]{Style.RESET_ALL}")
        for i, dtc in enumerate(result.dtcs, 1):
            print_dtc(dtc, i)


def progress_dot(module_name: str, index: int, total: int):
    """Simple progress indicator."""
    sys.stdout.write(f"\r  Scanning: {module_name:6s} ({index+1}/{total})  ")
    sys.stdout.flush()


# --- Menu Actions ---

def action_discover(scanner: DiagnosticScanner):
    """Discover which modules are online."""
    print(f"\n  {Style.BRIGHT}Discovering modules...{Style.RESET_ALL}")
    results = scanner.discover_modules(progress_callback=progress_dot)
    print("\r" + " " * 50 + "\r")  # Clear progress line

    print_separator()
    print(f"  {Style.BRIGHT}Module Status:{Style.RESET_ALL}\n")

    online = 0
    for result in results:
        mod = result.module
        if result.is_present:
            print(f"  {Fore.GREEN}●{Style.RESET_ALL} {mod.short_name:6s} - {mod.description}")
            online += 1
        else:
            print(f"  {Fore.WHITE}○{Style.RESET_ALL} {mod.short_name:6s} - {mod.description}")

    print(f"\n  {online}/{len(results)} modules responding")
    print_separator()


def action_scan_all(scanner: DiagnosticScanner):
    """Scan all modules for DTCs."""
    print(f"\n  {Style.BRIGHT}Scanning all modules for faults...{Style.RESET_ALL}")
    results = scanner.scan_all_modules(progress_callback=progress_dot)
    print("\r" + " " * 50 + "\r")

    print_separator()
    print(f"  {Style.BRIGHT}Scan Results:{Style.RESET_ALL}\n")

    total_dtcs = 0
    for result in results:
        if result.is_present:
            print_module_result(result)
            total_dtcs += len(result.dtcs)

    print(f"\n  Total: {total_dtcs} DTC(s) across all modules")
    print_separator()


def action_scan_module(scanner: DiagnosticScanner):
    """Scan a specific module for DTCs."""
    print(f"\n  Available modules: {', '.join(get_all_module_names())}")
    name = input(f"\n  Enter module name: ").strip()

    module = get_module_by_name(name)
    if not module:
        print_error(f"Unknown module '{name}'")
        return

    print_info(f"Scanning {module.short_name} ({module.description})...")
    result = scanner.scan_module_dtcs(module)

    print_separator()
    print_module_result(result)
    print_separator()


def action_clear_module(scanner: DiagnosticScanner):
    """Clear DTCs on a specific module."""
    print(f"\n  Available modules: {', '.join(get_all_module_names())}")
    name = input(f"\n  Enter module name: ").strip()

    module = get_module_by_name(name)
    if not module:
        print_error(f"Unknown module '{name}'")
        return

    print_warning(f"This will clear all DTCs on {module.short_name} ({module.description})")
    print_warning("Ensure: Ignition ON, Engine OFF")
    confirm = input(f"  Proceed? (y/n): ").strip().lower()

    if confirm != 'y':
        print_info("Cancelled")
        return

    print_info(f"Clearing DTCs on {module.short_name}...")
    result = scanner.clear_module_dtcs(module)

    if result.success:
        print_success(result.message)
    else:
        print_error(result.message)


def action_clear_all(scanner: DiagnosticScanner):
    """Clear DTCs on all responding modules."""
    print_warning("This will clear ALL DTCs on ALL responding modules!")
    print_warning("Ensure: Ignition ON, Engine OFF")
    confirm = input(f"  Type 'CLEAR ALL' to confirm: ").strip()

    if confirm != "CLEAR ALL":
        print_info("Cancelled")
        return

    print_info("Clearing all DTCs...")
    results = scanner.clear_all_dtcs(progress_callback=progress_dot)
    print("\r" + " " * 50 + "\r")

    print_separator()
    for module_name, result in results.items():
        if result.success:
            print_success(f"{module_name}: {result.message}")
        else:
            print_error(f"{module_name}: {result.message}")
    print_separator()


def action_module_info(scanner: DiagnosticScanner):
    """Read ECU identification from a module."""
    print(f"\n  Available modules: {', '.join(get_all_module_names())}")
    name = input(f"\n  Enter module name: ").strip()

    module = get_module_by_name(name)
    if not module:
        print_error(f"Unknown module '{name}'")
        return

    print_info(f"Reading info from {module.short_name}...")
    result = scanner.read_module_info(module)

    print_separator()
    if result.is_present:
        print(f"  {Style.BRIGHT}{module.short_name} - {module.description}{Style.RESET_ALL}")
        print(f"  CAN Request ID:  0x{module.request_id:03X}")
        print(f"  CAN Response ID: 0x{module.response_id:03X}")
        if result.ecu_part_number:
            print(f"  Part Number:     {result.ecu_part_number}")
        if result.ecu_software:
            print(f"  Software:        {result.ecu_software}")
    else:
        print_error(f"{module.short_name} not responding")
        if result.error:
            print_error(result.error)
    print_separator()


# --- Main Menu ---

def main_menu(scanner: DiagnosticScanner):
    """Interactive main menu loop."""
    while True:
        print(f"\n  {Style.BRIGHT}Main Menu:{Style.RESET_ALL}")
        print(f"  1. Discover online modules")
        print(f"  2. Scan ALL modules for faults")
        print(f"  3. Scan specific module")
        print(f"  4. Clear faults on specific module")
        print(f"  5. Clear ALL faults (all modules)")
        print(f"  6. Read module info (part number/software)")
        print(f"  0. Exit")
        print()

        choice = input(f"  Select [{Fore.CYAN}0-6{Style.RESET_ALL}]: ").strip()

        try:
            if choice == "1":
                action_discover(scanner)
            elif choice == "2":
                action_scan_all(scanner)
            elif choice == "3":
                action_scan_module(scanner)
            elif choice == "4":
                action_clear_module(scanner)
            elif choice == "5":
                action_clear_all(scanner)
            elif choice == "6":
                action_module_info(scanner)
            elif choice == "0":
                break
            else:
                print_warning("Invalid choice")
        except ELM327Error as e:
            print_error(f"Communication error: {e}")
            print_info("Check adapter connection and try again")
        except KeyboardInterrupt:
            print("\n")
            continue


# --- Entry Point ---

def main():
    parser = argparse.ArgumentParser(
        description="Range Rover Sport L494 Multi-Module Diagnostic Tool"
    )
    parser.add_argument(
        "--port", "-p",
        help="Serial port for ELM327 adapter (e.g., COM3, /dev/ttyUSB0)"
    )
    parser.add_argument(
        "--baud", "-b", type=int, default=115200,
        help="Serial baud rate (default: 115200, standard for OHP/FORScan adapters)"
    )
    parser.add_argument(
        "--list-ports", "-l", action="store_true",
        help="List available serial ports and exit"
    )
    args = parser.parse_args()

    print_header()

    # List ports mode
    if args.list_ports:
        ports = ELM327.list_ports()
        if ports:
            print(f"  Available serial ports:")
            for p in ports:
                print(f"    - {p}")
        else:
            print_warning("No serial ports detected")
        return

    # Determine port
    port = args.port
    if not port:
        ports = ELM327.list_ports()
        if not ports:
            print_error("No serial ports detected!")
            print_info("Connect your ELM327 adapter and try again")
            print_info("Or specify port manually: python main.py --port COM3")
            sys.exit(1)
        elif len(ports) == 1:
            port = ports[0]
            print_info(f"Auto-selected port: {port}")
        else:
            print(f"  Multiple ports found:")
            for i, p in enumerate(ports, 1):
                print(f"    {i}. {p}")
            choice = input(f"\n  Select port [1-{len(ports)}]: ").strip()
            try:
                port = ports[int(choice) - 1]
            except (ValueError, IndexError):
                print_error("Invalid selection")
                sys.exit(1)

    # Connect to adapter
    print_info(f"Connecting to ELM327 on {port} at {args.baud} baud...")
    elm = ELM327(port=port, baudrate=args.baud)

    try:
        version = elm.connect()
        print_success(f"Connected: {version}")
    except ELM327Error as e:
        print_error(f"Connection failed: {e}")
        print_info("Check that:")
        print_info("  - Adapter is plugged into vehicle OBD2 port")
        print_info("  - Ignition is ON")
        print_info("  - USB/Bluetooth is connected to laptop")
        sys.exit(1)

    # Run scanner
    scanner = DiagnosticScanner(elm)
    print_info("Vehicle ignition must be ON for communication")
    print_separator()

    try:
        main_menu(scanner)
    except KeyboardInterrupt:
        print(f"\n\n  Interrupted")
    finally:
        print_info("Disconnecting...")
        elm.disconnect()
        print_success("Done")


if __name__ == "__main__":
    main()
