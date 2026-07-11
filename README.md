# Range Rover Sport L494 Multi-Module Diagnostic Tool

A Python-based diagnostic tool for the 2014 Range Rover Sport (L494) that communicates
with multiple ECUs via the OBD2 port using UDS (Unified Diagnostic Services) protocol.

## Features

- **Multi-module scanning** - Engine (PCM), Transmission (TCM), Body Control Module (BCM),
  Air Suspension, Instrument Cluster, Parking Aid, Steering, ABS/DSC, and more
- **Read DTCs** - Read Diagnostic Trouble Codes from any supported module
- **Clear DTCs** - Reset/clear fault codes on individual modules or all at once
- **BCM Protected Output Reset** - Re-enable solid-state drivers disabled by overcurrent
  protection (U1000/U3000 faults — turn signals, headlamps, tail lamps)
- **Routine Control (0x31)** - Execute ECU routines for advanced reset functions
- **Security Access (0x27)** - Seed/key authentication for protected operations
- **ECU Reset (0x11)** - Soft/hard reset individual modules
- **Module identification** - Read ECU part numbers and software versions
- **Interactive CLI** - Easy-to-use terminal interface

## Hardware Requirements

- **OBD2 Adapter**: ELM327 v1.5+ compatible adapter (USB or Bluetooth)
  - Tested with: OHP (OBDHighPerformance) USB adapter (FORScan compatible)
  - Also works with: OBDLink SX, BAFX Products, or any genuine ELM327 v1.5+
  - Must support 500 kbps CAN (HS-CAN) — the OHP adapter does this natively
- **OBD2 Cable**: Standard 16-pin OBD2 connector (plugs under dashboard, driver side)
- **Laptop**: Windows, macOS, or Linux with Python 3.9+

## Installation

```bash
# Navigate to project directory
cd "JLR software clone"

# Create a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

# Install dependencies
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

## Supported Modules (2014 Range Rover Sport L494)

| Module | Description | CAN Request ID | CAN Response ID |
|--------|-------------|----------------|-----------------|
| PCM | Engine Control | 0x7E0 | 0x7E8 |
| TCM | Transmission Control | 0x7E1 | 0x7E9 |
| BCM | Body Control Module | 0x720 | 0x728 |
| RFA | Remote Function Actuator | 0x727 | 0x72F |
| IPC | Instrument Panel Cluster | 0x721 | 0x729 |
| ABS | ABS / Dynamic Stability | 0x760 | 0x768 |
| RCM | Restraint Control (Airbags) | 0x740 | 0x748 |
| EAS | Air Suspension | 0x723 | 0x72B |
| EPAS | Electric Power Steering | 0x730 | 0x738 |
| PAM | Parking Aid Module | 0x764 | 0x76C |
| HVAC | Climate Control | 0x724 | 0x72C |
| TPMS | Tire Pressure Monitoring | 0x725 | 0x72D |

> **Note**: CAN IDs may vary by model year and market specification. These are common
> addresses for the L494 platform. The tool will attempt communication and report which
> modules respond.

## Important Disclaimers

- **Use at your own risk.** Incorrect diagnostic commands can potentially affect vehicle
  operation. Always ensure the vehicle is in a safe state (parked, ignition on/engine off
  for clearing codes).
- **This tool does NOT replace professional diagnostic equipment** like JLR SDD/Pathfinder.
  It cannot perform module programming, calibration, or CCF configuration.
- **Clearing codes does not fix underlying problems.** If a fault returns after clearing,
  the root cause needs to be addressed.

## BCM Protected Output Diagnostic (U1000 / U3000)

The BCM uses FET (solid-state) drivers for lighting circuits. When it detects overcurrent
(e.g., a short in a taillight), it disables that output and sets U1000 ("Solid State Driver
Protection Activated"). A standard DTC clear alone may not re-enable the output.

Menu option 7 performs an **honest diagnostic procedure** — it does NOT blindly fire
guessed routine IDs at the BCM. Instead:

1. Verifies BCM communication and identifies it (part number / software)
2. Reads all BCM DTCs and identifies protection-related codes (U1xxx/U3xxx)
3. Performs a standard DTC clear (service 0x14) — clearly labeled as such
4. Re-scans the BCM to check if the protection fault returns immediately
5. Reports findings and recommends next steps

**If a standard clear does not resolve the issue**, the protected output requires a
specific Routine Control (service 0x31) command with the correct routine ID for your
BCM software version. This ID must come from:
- JLR service documentation
- A captured SDD/Pathfinder CAN session
- Community-verified data for your specific BCM part number

Once you have the correct routine ID, menu option 8 lets you execute it directly.

### What this tool will NOT do

- Guess routine IDs and fire them at the BCM
- Treat a timeout or "no response" as success
- Claim a DTC clear equals a protected output reset
- Send ECU reset commands as a speculative workaround

## License

MIT License
