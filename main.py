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
import os
import sys
import time
from datetime import datetime

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
from sniffer import CANSniffer, CANFrame
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


def action_bcm_reset_protected(scanner: DiagnosticScanner):
    """BCM Enable Protected Outputs using verified routine 0x205E."""
    print(f"\n  {Style.BRIGHT}BCM Enable Protected Outputs (Routine 0x205E){Style.RESET_ALL}")
    print(f"  {'─'*50}")
    print(f"  This executes the factory procedure to re-enable BCM outputs")
    print(f"  that were shut down due to overcurrent (U1000-00).")
    print()
    print(f"  Source: JLR DTC U1000-00 official diagnosis procedure")
    print(f"  Routine: 0x205E (Enable Protected Outputs)")
    print(f"  Path in SDD: Service Functions > Body systems > Enable Protected Outputs")
    print()
    print(f"  The procedure will:")
    print(f"    1. Verify BCM communication and identify it")
    print(f"    2. Read DTCs to confirm U1000 is present")
    print(f"    3. Start extended diagnostic session")
    print(f"    4. Execute Routine Control 0x31 with routine ID 0x205E")
    print(f"    5. Re-scan to verify protection DTCs cleared")
    print()
    print_warning("IMPORTANT: The short circuit must be fixed FIRST!")
    print_warning("If the fault still exists, the output will immediately trip again.")
    print_warning("Ensure: Ignition ON, Engine OFF, battery well charged.")
    print()
    confirm = input(f"  Proceed? (y/n): ").strip().lower()

    if confirm != 'y':
        print_info("Cancelled")
        return

    print()

    def log_line(msg):
        print(f"  {msg}")

    result = scanner.reset_bcm_protected_outputs(log_callback=log_line)

    print_separator()
    if result.success:
        print_success("Enable Protected Outputs procedure completed")
    else:
        print_error("Procedure did not complete successfully")
    print_separator()


def action_execute_routine(scanner: DiagnosticScanner):
    """Execute a known routine ID on a module (advanced)."""
    print(f"\n  {Style.BRIGHT}Execute Known Routine (Advanced){Style.RESET_ALL}")
    print(f"  {'─'*45}")
    print_warning("Only use this if you have a VERIFIED routine ID from")
    print_warning("JLR documentation or a captured SDD/Pathfinder session.")
    print()
    print(f"  Available modules: {', '.join(get_all_module_names())}")
    name = input(f"\n  Module name: ").strip()

    module = get_module_by_name(name)
    if not module:
        print_error(f"Unknown module '{name}'")
        return

    routine_hex = input(f"  Routine ID (hex, e.g. 0203): ").strip()
    try:
        routine_id = int(routine_hex, 16)
    except ValueError:
        print_error("Invalid hex value")
        return

    print()
    print_info(f"Module: {module.short_name} ({module.description})")
    print_info(f"Routine: 0x{routine_id:04X}")
    print_info(f"Sub-function: 0x01 (Start Routine)")
    print()
    confirm = input(f"  Send this routine? (y/n): ").strip().lower()
    if confirm != 'y':
        print_info("Cancelled")
        return

    result = scanner.execute_known_routine(
        module_name=module.short_name,
        routine_id=routine_id,
    )

    print_separator()
    if result.success:
        print_success(result.message)
    else:
        print_error(result.message)
    print_separator()


def action_can_sniffer(elm: ELM327):
    """CAN bus passive sniffer for capturing diagnostic traffic."""
    print(f"\n  {Style.BRIGHT}CAN Bus Sniffer (Passive Monitor){Style.RESET_ALL}")
    print(f"  {'─'*45}")
    print(f"  Captures CAN frames flowing between another diagnostic tool")
    print(f"  (e.g., JLR SDD/Pathfinder) and the vehicle's ECUs.")
    print()
    print(f"  Setup:")
    print(f"  - Y-splitter on OBD2 port: SDD tool + your OHP adapter")
    print(f"  - Your adapter passively listens (does not transmit)")
    print(f"  - Start capture BEFORE running the SDD procedure")
    print()
    print(f"  Filter options:")
    print(f"  1. Capture ALL diagnostic traffic (0x700-0x7FF)")
    print(f"  2. Capture BCM only (0x720 / 0x728)")
    print(f"  3. Capture specific ECU pair")
    print()

    choice = input(f"  Filter [{Fore.CYAN}1-3{Style.RESET_ALL}]: ").strip()

    filter_id = None
    filter_mask = None

    if choice == "2":
        filter_id = 0x720
        filter_mask = 0x7F0  # Matches 0x720-0x72F (covers request + response)
    elif choice == "3":
        id_hex = input(f"  Enter CAN ID to filter (hex, e.g. 720): ").strip()
        try:
            filter_id = int(id_hex, 16)
            filter_mask = 0x7F0  # Match that ECU pair
        except ValueError:
            print_error("Invalid hex value, capturing all")
            filter_id = None

    duration_str = input(f"  Capture duration in seconds [60]: ").strip()
    try:
        duration = float(duration_str) if duration_str else 60.0
    except ValueError:
        duration = 60.0

    print()
    print_info(f"Starting capture for {duration:.0f} seconds...")
    print_info("Press Ctrl+C to stop early")
    print_separator()
    print(f"  {'Timestamp':>10s}  {'CAN ID':>6s}  Len  {'Data':<24s}  Direction")
    print(f"  {'─'*70}")

    frame_count = [0]

    def on_frame(frame: CANFrame):
        # Only display diagnostic-range frames
        if frame.is_diagnostic:
            frame_count[0] += 1
            print(f"  {frame.timestamp:10.3f}  {frame.id_hex}  "
                  f"[{len(frame.data)}]  {frame.data_hex:<24s}  "
                  f"{frame.direction}")

    sniffer = CANSniffer(elm)
    try:
        frames = sniffer.start_monitor(
            filter_id=filter_id,
            filter_mask=filter_mask,
            duration=duration,
            callback=on_frame,
        )
    except ELM327Error as e:
        print_error(f"Sniffer error: {e}")
        return

    print_separator()
    diag_frames = sniffer.get_diagnostic_frames()
    print_info(f"Captured {len(frames)} total frames, "
               f"{len(diag_frames)} in diagnostic range")

    # Analyze for routine control commands
    routines = sniffer.analyze_routine_control()
    if routines:
        print()
        print(f"  {Style.BRIGHT}Routine Control (0x31) commands found:{Style.RESET_ALL}")
        for r in routines:
            print(f"    {r['timestamp']:.3f}s  Target: {r['target_id']}  "
                  f"Routine: {r['routine_id']}  Sub: 0x{r['sub_function']:02X}  "
                  f"{r['direction']}")
            if r['option_record']:
                print(f"      Option bytes: {r['option_record']}")
        print()
        print_success("These are the routine IDs you need!")
        print_info("Use menu option 8 to replay a captured routine.")

    # Save to file
    if diag_frames:
        print()
        save = input(f"  Save capture to file? (y/n): ").strip().lower()
        if save == 'y':
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"can_capture_{timestamp}.log"
            filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    filename)
            sniffer.save_log(filepath, diag_frames)
            print_success(f"Saved {len(diag_frames)} frames to {filename}")

            # Also save BCM-specific if there are BCM frames
            bcm_count = sniffer.save_bcm_session(
                filepath.replace(".log", "_bcm.log")
            )
            if bcm_count > 0:
                print_success(f"Saved {bcm_count} BCM frames to "
                              f"{filename.replace('.log', '_bcm.log')}")


# --- Main Menu ---

def main_menu(scanner: DiagnosticScanner, elm: ELM327):
    """Interactive main menu loop."""
    while True:
        print(f"\n  {Style.BRIGHT}Main Menu:{Style.RESET_ALL}")
        print(f"  1. Discover online modules")
        print(f"  2. Scan ALL modules for faults")
        print(f"  3. Scan specific module")
        print(f"  4. Clear faults on specific module")
        print(f"  5. Clear ALL faults (all modules)")
        print(f"  6. Read module info (part number/software)")
        print(f"  7. {Fore.YELLOW}BCM Enable Protected Outputs{Style.RESET_ALL} (routine 0x205E)")
        print(f"  8. Execute known routine (advanced)")
        print(f"  9. {Fore.MAGENTA}CAN Bus Sniffer{Style.RESET_ALL} (capture SDD traffic)")
        print(f"  0. Exit")
        print()

        choice = input(f"  Select [{Fore.CYAN}0-9{Style.RESET_ALL}]: ").strip()

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
            elif choice == "7":
                action_bcm_reset_protected(scanner)
            elif choice == "8":
                action_execute_routine(scanner)
            elif choice == "9":
                action_can_sniffer(elm)
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
        main_menu(scanner, elm)
    except KeyboardInterrupt:
        print(f"\n\n  Interrupted")
    finally:
        print_info("Disconnecting...")
        elm.disconnect()
        print_success("Done")


if __name__ == "__main__":
    main()
