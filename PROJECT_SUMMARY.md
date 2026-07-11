# Project Summary

## What This Is

A Python diagnostic tool for the 2014 Range Rover Sport (L494) that talks to the
vehicle's ECU modules through the OBD2 port using a USB ELM327-compatible adapter.
Built specifically to fix a dead right-rear turn signal caused by water ingress in
a cracked taillight housing, which triggered the BCM's solid-state driver protection.

## The Problem

Water got into the cracked taillight housing, shorted the lamp circuit, and the Body
Control Module (BCM) detected overcurrent. The BCM disabled the output (a FET/solid-state
driver) and set DTC U1000-00: "Solid State Driver Protection Active - Driver Disabled."

A standard DTC clear does not re-enable the output. The BCM stores the protection state
in non-volatile memory — it survives battery disconnects. The only fix is a specific UDS
Routine Control command that JLR calls "Enable Protected Outputs."

## The Solution

The tool sends the verified factory command to the BCM:

```
CAN ID:  0x720 (BCM request)
Payload: 31 01 20 5E

31    = RoutineControl (UDS service)
01    = Start Routine
20 5E = Routine ID 0x205E (Enable Protected Outputs)
```

Expected positive response from 0x728: `71 01 20 5E`

## Source of Routine ID 0x205E

JLR's official DTC U1000-00 diagnostic procedure states:

> "To re-enable the output circuits, using the Jaguar Land Rover approved diagnostic
> equipment, perform the routine - Enable Protected Outputs (205E). The routine can
> be located on the diagnostic equipment within BCM - ECU functions."

Also documented in JLR Special Service Message SSM74176:
- SDD path: Service Functions → Body systems → Enable Protected Outputs
- Pathfinder path: ECU Diagnostics → BCM → ECU Functions → Enable Protected Outputs
- Applies to: L494 14MY+, L405 14MY+, L538 14MY+, L550 15MY+, L462 17MY+, L560 18MY+

## Hardware

- **Adapter**: OHP (OBDHighPerformance) USB adapter, FORScan compatible
- **Baud rate**: 500000 (adapter to PC serial)
- **CAN bus**: 500 kbps, 11-bit IDs, ISO 15765-4 (Protocol 6 on ELM327)
- **Note**: Adapter requires 12V from OBD2 port to power on — won't respond over USB alone

## How to Use

```bash
git clone https://github.com/MrUnggoy/rr-sport-l494-diag.git
cd rr-sport-l494-diag
pip install -r requirements.txt
python main.py --port COM3 --baud 500000
```

Then select option 7: "BCM Enable Protected Outputs"

The procedure:
1. Verifies BCM is responding at 0x720/0x728
2. Reads BCM part number and software version
3. Reads all DTCs and confirms U1000 is present
4. Starts extended diagnostic session (0x10 0x03)
5. Executes routine 0x205E (31 01 20 5E)
6. Clears all DTCs (14 FF FF FF)
7. Re-scans to verify protection DTCs are gone

After completion: turn ignition OFF, wait 10 seconds, turn back ON, test the light.

## Full Menu

| # | Function |
|---|----------|
| 1 | Discover online modules (ping all 14 ECUs) |
| 2 | Scan all modules for faults |
| 3 | Scan specific module |
| 4 | Clear faults on specific module |
| 5 | Clear all faults (all modules) |
| 6 | Read module info (part number/software) |
| 7 | BCM Enable Protected Outputs (routine 0x205E) |
| 8 | Execute any known routine by ID (advanced) |
| 9 | CAN bus sniffer (passive traffic capture) |

## Known Modules (L494)

| Module | Description | Request | Response |
|--------|-------------|---------|----------|
| PCM | Engine | 0x7E0 | 0x7E8 |
| TCM | Transmission | 0x7E1 | 0x7E9 |
| BCM | Body Control | 0x720 | 0x728 |
| IPC | Instrument Cluster | 0x721 | 0x729 |
| EAS | Air Suspension | 0x723 | 0x72B |
| HVAC | Climate Control | 0x724 | 0x72C |
| TPMS | Tire Pressure | 0x725 | 0x72D |
| RFA | Remote/Key/Lock | 0x727 | 0x72F |
| EPAS | Power Steering | 0x730 | 0x738 |
| RCM | Airbags | 0x740 | 0x748 |
| ABS | Braking/Stability | 0x760 | 0x768 |
| PAM | Parking Aid | 0x764 | 0x76C |
| ACC | Adaptive Cruise | 0x766 | 0x76E |
| AHBC | Adaptive Headlamp | 0x769 | 0x771 |

## What Was Learned

- The OHP adapter runs at 500000 baud (not 115200 or 38400)
- ELM327 timeout needs to be ~1 second (ATSTFA) for JLR modules which respond slowly
- BCM DTC clear returns NRC 0x78 (Response Pending) before the real response — code must wait
- Multi-frame ISO-TP responses come as "0:hex 1:hex 2:hex..." and need assembly
- The BCM protection state survives battery disconnects (stored in EEPROM)
- JLR uses EXML files (Triple DES encrypted XML) to store all routine IDs and security keys
- The smartgauges/exml tool on GitHub can decrypt them
- SDD is a VirtualBox VM with SA_*.dll plugins that implement each diagnostic routine

## Potential Issues When Running Option 7

- **Security access required**: If the BCM responds with NRC 0x33 (Security Access Denied),
  it needs a seed-to-key unlock (service 0x27) before the routine. The key algorithm is in
  JLR's SecAlg.dll / Security.exml files.
- **Wrong session type**: If NRC 0x7F (Service Not Supported In Active Session), try
  programming session (0x02) instead of extended (0x03).
- **Conditions not correct**: If NRC 0x22, ensure ignition is ON and engine is OFF.
- **Short still present**: If U1000 returns immediately after the routine, the wiring
  fault isn't actually fixed.

## File Structure

```
main.py          - Interactive CLI menu
elm327.py        - ELM327 serial communication layer
uds.py           - UDS protocol (ISO 14229) services
scanner.py       - High-level multi-module scanner + BCM routine
modules.py       - ECU module definitions with CAN IDs
sniffer.py       - Passive CAN bus traffic capture
debug_*.py       - Raw debug scripts used during development
requirements.txt - pyserial, colorama
```

## Repository

https://github.com/MrUnggoy/rr-sport-l494-diag
