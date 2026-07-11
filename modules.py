"""
ECU Module definitions for 2014 Range Rover Sport (L494).

Each module is defined with its name, description, and CAN arbitration IDs
used for UDS diagnostic communication via the OBD2 port.

The L494 uses CAN bus at 500 kbps with ISO 15765-4 (CAN) as the OBD transport.
Diagnostic services follow ISO 14229 (UDS).
"""

from dataclasses import dataclass


@dataclass
class ECUModule:
    """Represents a vehicle ECU module accessible via OBD2."""
    short_name: str
    description: str
    request_id: int  # CAN arbitration ID for requests (tester -> ECU)
    response_id: int  # CAN arbitration ID for responses (ECU -> tester)


# Known modules for the 2014 Range Rover Sport L494
# CAN IDs are based on common JLR addressing schemes.
# Standard OBD2 uses 0x7DF for broadcast, 0x7E0-0x7E7 for direct ECU addressing.
# JLR uses extended addressing for body/chassis modules in the 0x7xx range.

MODULES = [
    ECUModule(
        short_name="PCM",
        description="Powertrain Control Module (Engine)",
        request_id=0x7E0,
        response_id=0x7E8,
    ),
    ECUModule(
        short_name="TCM",
        description="Transmission Control Module",
        request_id=0x7E1,
        response_id=0x7E9,
    ),
    ECUModule(
        short_name="BCM",
        description="Body Control Module",
        request_id=0x720,
        response_id=0x728,
    ),
    ECUModule(
        short_name="IPC",
        description="Instrument Panel Cluster",
        request_id=0x721,
        response_id=0x729,
    ),
    ECUModule(
        short_name="EAS",
        description="Electronic Air Suspension",
        request_id=0x723,
        response_id=0x72B,
    ),
    ECUModule(
        short_name="HVAC",
        description="Heating Ventilation & Air Conditioning",
        request_id=0x724,
        response_id=0x72C,
    ),
    ECUModule(
        short_name="TPMS",
        description="Tire Pressure Monitoring System",
        request_id=0x725,
        response_id=0x72D,
    ),
    ECUModule(
        short_name="RFA",
        description="Remote Function Actuator (Key/Lock)",
        request_id=0x727,
        response_id=0x72F,
    ),
    ECUModule(
        short_name="EPAS",
        description="Electric Power Assisted Steering",
        request_id=0x730,
        response_id=0x738,
    ),
    ECUModule(
        short_name="RCM",
        description="Restraint Control Module (Airbags)",
        request_id=0x740,
        response_id=0x748,
    ),
    ECUModule(
        short_name="ABS",
        description="Anti-lock Braking / Stability Control",
        request_id=0x760,
        response_id=0x768,
    ),
    ECUModule(
        short_name="PAM",
        description="Parking Aid Module",
        request_id=0x764,
        response_id=0x76C,
    ),
    ECUModule(
        short_name="ACC",
        description="Adaptive Cruise Control",
        request_id=0x766,
        response_id=0x76E,
    ),
    ECUModule(
        short_name="AHBC",
        description="Adaptive Headlamp Beam Control",
        request_id=0x769,
        response_id=0x771,
    ),
]


def get_module_by_name(name: str) -> ECUModule | None:
    """Look up a module by its short name (case-insensitive)."""
    name_upper = name.upper()
    for mod in MODULES:
        if mod.short_name == name_upper:
            return mod
    return None


def get_all_module_names() -> list[str]:
    """Return list of all module short names."""
    return [m.short_name for m in MODULES]
