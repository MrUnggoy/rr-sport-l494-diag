# Range Rover Sport L494 Multi-Module Diagnostic Tool

A Python-based diagnostic tool for the 2014 Range Rover Sport (L494) that communicates
with multiple ECUs via the OBD2 port using UDS (Unified Diagnostic Services) protocol.

## Features

- **Multi-module scanning** - Discover and communicate with 14 ECUs: Engine (PCM),
  Transmission (TCM), Body Control Module (BCM), Air Suspension (EAS), Instrument
  Cluster (IPC), Parking Aid (PAM), Steering (EPAS), ABS/DSC, Airbags (RCM), and more
- **Read DTCs** - Read Diagnostic Trouble Codes from any supported module with full
  status reporting (active, confirmed, pending, MIL)
- **Clear DTCs** - Clear fault codes on individual modules or all at once
- **BCM Protected Output Diagnostic** - Investigate U1000/U3000 faults (solid-state
  driver protection), clear codes, re-scan to verify, and report honest results
- **Execute Known Routines** - Send a verified Routine Control (0x31) command to any
  module when you have the correct routine ID from JLR documentation or an SDD capture
- **Module identification** - Read ECU part numbers and software versions
- **Interactive CLI** - Color-coded terminal interface with step-by-step logging

## Hardware Requirements

- **OBD2 Adapter**: ELM327 v1.5+ compatible adapter (USB)
  - Tested with: OHP (OBDHighPerformance) USB adapter (FORScan compatible)
  - Also works with: OBDLink SX, BAFX Products, or any genuine ELM327 v1.5+
  - Must support 500 kbps CAN (HS-CAN) — the OHP adapter does this natively
  - Note: The adapter needs 12V from the OBD2 port to power on (won't respond over USB alone)
- **OBD2 Port**: Standard 16-pin connector, under dashboard, driver side
- **Laptop**: Windows, macOS, or Linux with Python 3.9+

## Installation

```bash
git clone https://github.com/MrUnggoy/rr-sport-l494-diag.git
cd rr-sport-l494-diag
pip install -r requirements.txt
```

## Usage

```bash
# Run the diagnostic tool
python main.py

# Specify a COM port explicitly
python main.py --port COM3

# Specify a baud rate (default: 115200 for OHP/FORScan adapters)
python main.py --port COM3 --baud 115200

# List available serial ports
python main.py --list-ports
```

## Menu Options

| # | Function | Description |
|---|----------|-------------|
| 1 | Discover modules | Ping all known ECUs, report which are online |
| 2 | Scan all modules | Read DTCs from every responding module |
| 3 | Scan specific module | Read DTCs from one module by name |
| 4 | Clear specific module | Clear DTCs on one module |
| 5 | Clear all modules | Clear DTCs on all responding modules |
| 6 | Read module info | Get part number / software version from a module |
| 7 | BCM Protected Output Diagnostic | Investigate U1000/U3000 faults (see below) |
| 8 | Execute known routine | Send a verified routine ID to any module (advanced) |
| 9 | CAN Bus Sniffer | Passive capture of diagnostic traffic (see below) |

## Supported Modules (2014 Range Rover Sport L494)

| Module | Description | CAN Request ID | CAN Response ID |
|--------|-------------|----------------|-----------------|
| PCM | Engine Control | 0x7E0 | 0x7E8 |
| TCM | Transmission Control | 0x7E1 | 0x7E9 |
| BCM | Body Control Module | 0x720 | 0x728 |
| IPC | Instrument Panel Cluster | 0x721 | 0x729 |
| EAS | Electronic Air Suspension | 0x723 | 0x72B |
| HVAC | Climate Control | 0x724 | 0x72C |
| TPMS | Tire Pressure Monitoring | 0x725 | 0x72D |
| RFA | Remote Function Actuator | 0x727 | 0x72F |
| EPAS | Electric Power Steering | 0x730 | 0x738 |
| RCM | Restraint Control (Airbags) | 0x740 | 0x748 |
| ABS | ABS / Dynamic Stability | 0x760 | 0x768 |
| PAM | Parking Aid Module | 0x764 | 0x76C |
| ACC | Adaptive Cruise Control | 0x766 | 0x76E |
| AHBC | Adaptive Headlamp Beam | 0x769 | 0x771 |

> **Note**: CAN IDs may vary by model year and market specification. The tool pings
> each address and reports which modules respond on your vehicle.

## BCM Protected Output Diagnostic (U1000 / U3000)

The BCM uses FET (solid-state) drivers for lighting circuits. When it detects overcurrent
(e.g., a short in a taillight), it disables that output and sets U1000 ("Solid State Driver
Protection Activated"). A standard DTC clear alone may not re-enable the output.

Menu option 7 performs an **honest diagnostic procedure**:

1. Verifies BCM communication and identifies it (part number / software version)
2. Reads all BCM DTCs and identifies protection-related codes (U1xxx/U3xxx)
3. Assesses whether protection DTCs are present
4. Performs a standard DTC clear (service 0x14) — clearly labeled as only a DTC clear
5. Re-scans the BCM to check if the protection fault returns immediately
6. Reports findings with honest conclusions and recommended next steps

**If a standard clear does not resolve the issue**, the protected output requires a
specific Routine Control (service 0x31) command with the correct routine ID for your
BCM software version. This ID must come from:
- JLR service documentation
- A captured SDD/Pathfinder CAN bus trace
- Community-verified data for your specific BCM part number

Once you have the correct routine ID, menu option 8 lets you execute it.

### Design principles

This tool will NOT:
- Guess routine IDs and fire them at the BCM
- Treat a timeout or "no response" as success
- Claim a DTC clear equals a protected output reset
- Send ECU reset commands as a speculative workaround
- Report success without a confirmed positive UDS response

## CAN Bus Sniffer (Menu Option 9)

Passive monitoring mode that captures CAN traffic between another diagnostic tool
(JLR SDD/Pathfinder, IIDTool, etc.) and the vehicle. This is how you obtain the
exact routine ID needed for "Enable Protected Outputs."

### Setup

1. Get an OBD2 Y-splitter cable
2. Plug the shop's SDD interface into one leg, your OHP adapter into the other
3. Start the sniffer (option 9) BEFORE the tech runs the procedure
4. Select BCM filter (option 2) to reduce noise
5. The tech runs "Enable Protected Outputs" in SDD
6. Stop the capture — the tool automatically identifies Routine Control (0x31)
   commands and shows you the exact routine ID and parameters

### What it captures

- All CAN frames in the diagnostic range (0x700-0x7FF)
- Timestamps for each frame
- Direction detection (tester to ECU vs ECU to tester)
- Automatic identification of Routine Control (0x31) commands
- Save to timestamped log files for later analysis

### After capture

The sniffer displays any 0x31 Routine Control commands it finds, including:
- Target ECU CAN ID
- Routine ID (the 2-byte hex value you need)
- Sub-function (start/stop/results)
- Option record bytes (if any)

Take the routine ID from the capture and use it in menu option 8 to replay the
exact same command yourself, without needing the expensive tool again.

## JLR SSM74176 Reference

This tool addresses the procedure documented in JLR Special Service Message SSM74176:
"Body Control Module Outputs Not Functioning with DTC U1000-00 stored."

Applies to: L494 (Range Rover Sport) 14MY onwards, L405, L538, L550, L462, L560.

The official SDD procedure is: Service Functions > "Body systems - Enable Protected Outputs"

The official Pathfinder path is: ECU Diagnostics > BCM > ECU Functions > "Enable Protected Outputs"

Both execute a UDS Routine Control command underneath. This tool provides the means to
capture and replay that command without a dealer subscription.

### UDS services available in the code

The UDS layer supports these services for use when you have verified parameters:
- **Diagnostic Session Control (0x10)** - Default / Extended / Programming sessions
- **Security Access (0x27)** - Seed request and key send (algorithm must be provided)
- **Routine Control (0x31)** - Start / Stop / Request Results with any routine ID
- **ECU Reset (0x11)** - Hard / Soft / Key-off-on reset
- **Clear DTC (0x14)** - Clear by group or all
- **Read DTC Info (0x19)** - By status mask, count, or supported
- **Read Data By ID (0x22)** - Read DIDs (part numbers, versions, etc.)
- **Tester Present (0x3E)** - Session keep-alive

## Important Disclaimers

- **Use at your own risk.** Incorrect diagnostic commands can affect vehicle operation.
  Always ensure the vehicle is parked with ignition on / engine off.
- **This tool does NOT replace JLR SDD/Pathfinder.** It cannot perform module
  programming, calibration, CCF configuration, or security-locked routines without
  the correct key algorithm.
- **Clearing codes does not fix underlying problems.** If a fault returns after clearing,
  the root cause (wiring, component) must be addressed.
- **CAN addresses are assumed.** The tool verifies each module responds before
  proceeding, but cannot guarantee the responder is the expected module without
  reading its identification.

## License

MIT License
