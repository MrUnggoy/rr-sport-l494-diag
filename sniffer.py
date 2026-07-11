"""
CAN Bus Sniffer / Logger for capturing diagnostic traffic.

Puts the ELM327 adapter into a passive monitoring mode to capture CAN frames
flowing between a diagnostic tool (e.g., JLR SDD/Pathfinder) and vehicle ECUs.

Use case: Capture the exact UDS commands SDD sends when performing
"Enable Protected Outputs" on the BCM, then replay them with this tool.

Setup:
  - Y-splitter on the OBD2 port (both SDD interface and your adapter plugged in)
  - Or: Use a CAN tap on the HS-CAN lines (pins 6 & 14)
  - Your adapter must NOT transmit during capture (passive mode)
"""

import time
import os
from datetime import datetime

from elm327 import ELM327, ELM327Error


class CANFrame:
    """Represents a single captured CAN frame."""

    def __init__(self, timestamp: float, arb_id: int, data: bytes):
        self.timestamp = timestamp
        self.arb_id = arb_id
        self.data = data

    @property
    def id_hex(self) -> str:
        return f"0x{self.arb_id:03X}"

    @property
    def data_hex(self) -> str:
        return " ".join(f"{b:02X}" for b in self.data)

    @property
    def is_diagnostic(self) -> bool:
        """Check if this frame is in the UDS diagnostic ID range."""
        return (0x700 <= self.arb_id <= 0x7FF)

    @property
    def direction(self) -> str:
        """Guess direction based on CAN ID convention."""
        # Standard: 0x7Ex = request (tester->ECU), 0x7Ex+8 = response (ECU->tester)
        # JLR body: 0x72x = request, 0x72x+8 = response
        if self.arb_id in (0x7DF,):  # Broadcast
            return "TESTER->ALL"
        low_nibble = self.arb_id & 0x0F
        if low_nibble < 8:
            return "TESTER->ECU"
        else:
            return "ECU->TESTER"

    def __str__(self) -> str:
        return (f"{self.timestamp:.3f}  {self.id_hex}  "
                f"[{len(self.data)}]  {self.data_hex}  "
                f"  {self.direction}")


class CANSniffer:
    """
    Passive CAN bus monitor using ELM327 in monitor mode.
    
    ELM327 supports a Monitor All (ATMA) command that puts it into
    receive-only mode, capturing all CAN frames on the bus.
    """

    def __init__(self, elm: ELM327):
        self.elm = elm
        self._frames: list[CANFrame] = []
        self._start_time: float = 0
        self._running: bool = False

    def start_monitor(self, filter_id: int | None = None,
                      filter_mask: int | None = None,
                      duration: float = 60.0,
                      callback=None) -> list[CANFrame]:
        """
        Start passive CAN monitoring.
        
        Args:
            filter_id: Only capture frames matching this ID (None = all).
            filter_mask: Mask for ID filtering (e.g., 0x7F8 to match 0x720-0x727).
            duration: Maximum capture time in seconds.
            callback: Optional callable(frame) for live display.
            
        Returns:
            List of captured CANFrame objects.
        """
        if not self.elm._serial or not self.elm._serial.is_open:
            raise ELM327Error("Not connected")

        self._frames = []
        self._start_time = time.time()

        # Configure filtering if requested
        if filter_id is not None:
            # Set CAN filter and mask
            self.elm._send_command(f"ATCF{filter_id:03X}")
            if filter_mask is not None:
                self.elm._send_command(f"ATCM{filter_mask:03X}")
            else:
                self.elm._send_command("ATCM7FF")  # Exact match
        else:
            # Clear any existing filter
            self.elm._send_command("ATAR")

        # Disable headers in data (we'll parse the full frame)
        # Actually, we WANT headers to see the CAN IDs
        self.elm._send_command("ATH1")  # Headers ON
        self.elm._send_command("ATS1")  # Spaces ON (easier parsing)
        self.elm._send_command("ATCAF0")  # CAN auto-formatting OFF (raw frames)

        # Enter Monitor All mode
        self.elm._serial.reset_input_buffer()
        self.elm._serial.write(b"ATMA\r")
        self._running = True

        try:
            buffer = ""
            while self._running:
                elapsed = time.time() - self._start_time
                if elapsed >= duration:
                    break

                # Read available data
                if self.elm._serial.in_waiting:
                    chunk = self.elm._serial.read(
                        self.elm._serial.in_waiting
                    ).decode("ascii", errors="ignore")
                    buffer += chunk

                    # Process complete lines
                    while "\r" in buffer:
                        line, buffer = buffer.split("\r", 1)
                        line = line.strip()
                        if not line:
                            continue
                        if line == ">":
                            # Monitor mode exited
                            self._running = False
                            break
                        if line in ("STOPPED", "?", "CAN ERROR", "BUFFER FULL"):
                            continue

                        frame = self._parse_frame(line, elapsed)
                        if frame:
                            self._frames.append(frame)
                            if callback:
                                callback(frame)
                else:
                    time.sleep(0.01)

        except KeyboardInterrupt:
            pass
        finally:
            # Stop monitoring - send any character to exit ATMA
            self.elm._serial.write(b"\r")
            time.sleep(0.3)
            # Read and discard remaining data
            if self.elm._serial.in_waiting:
                self.elm._serial.read(self.elm._serial.in_waiting)
            # Wait for prompt
            time.sleep(0.2)
            if self.elm._serial.in_waiting:
                self.elm._serial.read(self.elm._serial.in_waiting)

            # Restore normal settings
            self.elm._send_command("ATH0")  # Headers off
            self.elm._send_command("ATS0")  # Spaces off
            self.elm._send_command("ATCAF1")  # CAN auto-formatting on
            self.elm._send_command("ATAR")  # Clear filters
            self._running = False

        return self._frames

    def stop(self):
        """Signal the monitor to stop."""
        self._running = False

    def _parse_frame(self, line: str, timestamp: float) -> CANFrame | None:
        """
        Parse a raw ELM327 monitor line into a CANFrame.
        
        Format with headers ON, spaces ON:
          "720 03 19 02 FF"  (ID=0x720, data=03 19 02 FF)
          
        Format varies by ELM327 firmware. Common patterns:
          "7E0 02 3E 00"     (3-byte header, then data)
          "720 06 31 01 02 03 00 00"
        """
        parts = line.split()
        if len(parts) < 2:
            return None

        # First part should be the CAN arbitration ID (3 hex chars for 11-bit)
        try:
            arb_id = int(parts[0], 16)
        except ValueError:
            return None

        # Sanity check: 11-bit CAN IDs are 0x000-0x7FF
        if arb_id > 0x7FF:
            return None

        # Remaining parts are data bytes
        data_bytes = []
        for part in parts[1:]:
            try:
                data_bytes.append(int(part, 16))
            except ValueError:
                break

        if not data_bytes:
            return None

        return CANFrame(
            timestamp=timestamp,
            arb_id=arb_id,
            data=bytes(data_bytes),
        )

    def get_diagnostic_frames(self) -> list[CANFrame]:
        """Filter captured frames to only diagnostic range (0x700-0x7FF)."""
        return [f for f in self._frames if f.is_diagnostic]

    def get_frames_for_ecu(self, request_id: int, response_id: int) -> list[CANFrame]:
        """Get frames for a specific ECU conversation."""
        return [f for f in self._frames
                if f.arb_id in (request_id, response_id)]

    def save_log(self, filepath: str, frames: list[CANFrame] | None = None):
        """
        Save captured frames to a log file.
        
        Format: timestamp, CAN_ID, length, hex_data, direction
        """
        frames = frames or self._frames
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# CAN Bus Capture Log\n")
            f.write(f"# Date: {datetime.now().isoformat()}\n")
            f.write(f"# Frames: {len(frames)}\n")
            f.write(f"# Duration: {frames[-1].timestamp - frames[0].timestamp:.1f}s\n"
                    if len(frames) > 1 else "")
            f.write(f"#\n")
            f.write(f"# Timestamp    CAN_ID  Len  Data                     Direction\n")
            f.write(f"# {'─'*70}\n")
            for frame in frames:
                f.write(f"{frame.timestamp:10.3f}  "
                        f"{frame.id_hex}  "
                        f"[{len(frame.data)}]  "
                        f"{frame.data_hex:24s}  "
                        f"{frame.direction}\n")

    def save_bcm_session(self, filepath: str):
        """
        Save only BCM-related frames (0x720/0x728) to a log file.
        Useful for isolating the "Enable Protected Outputs" routine.
        """
        bcm_frames = self.get_frames_for_ecu(0x720, 0x728)
        if not bcm_frames:
            # Also check for functional addressing that might hit BCM
            bcm_frames = [f for f in self._frames
                          if f.arb_id in (0x720, 0x728, 0x7DF)]
        self.save_log(filepath, bcm_frames)
        return len(bcm_frames)

    def analyze_routine_control(self) -> list[dict]:
        """
        Find all Routine Control (0x31) requests in the captured data.
        Returns list of dicts with routine_id, target ECU, and full payload.
        """
        routines = []
        for frame in self._frames:
            if not frame.is_diagnostic:
                continue
            # Look for service 0x31 in the data
            # ISO-TP single frame: [PCI_length] [0x31] [sub] [ID_hi] [ID_lo] ...
            data = frame.data
            if len(data) >= 4:
                # Single frame: first byte is PCI (length)
                pci = data[0]
                if pci <= 7 and len(data) > pci:
                    payload = data[1:pci+1]
                    if len(payload) >= 4 and payload[0] == 0x31:
                        sub_func = payload[1]
                        routine_id = (payload[2] << 8) | payload[3]
                        option_record = payload[4:] if len(payload) > 4 else b""
                        routines.append({
                            "timestamp": frame.timestamp,
                            "target_id": frame.id_hex,
                            "sub_function": sub_func,
                            "routine_id": f"0x{routine_id:04X}",
                            "routine_id_int": routine_id,
                            "option_record": option_record.hex().upper() if option_record else "",
                            "full_payload": data.hex().upper(),
                            "direction": frame.direction,
                        })
        return routines
