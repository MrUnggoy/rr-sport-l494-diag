"""
ELM327 OBD2 Adapter Communication Layer.

Handles low-level serial communication with an ELM327-compatible OBD2 adapter.
Configures the adapter for CAN bus communication at 500 kbps (ISO 15765-4)
and provides methods to send/receive raw CAN frames for UDS messaging.
"""

import time
import serial
import serial.tools.list_ports


class ELM327Error(Exception):
    """Raised when ELM327 communication fails."""
    pass


class ELM327:
    """Interface to an ELM327 OBD2 adapter over serial."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 2.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: serial.Serial | None = None
        self._elm_version: str = ""

    @staticmethod
    def list_ports() -> list[str]:
        """List available serial/COM ports on the system."""
        ports = serial.tools.list_ports.comports()
        return [p.device for p in ports]

    def connect(self) -> str:
        """
        Open serial connection and initialize the ELM327 adapter.
        Returns the adapter version string.
        """
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                write_timeout=self.timeout,
            )
        except serial.SerialException as e:
            raise ELM327Error(f"Cannot open port {self.port}: {e}")

        time.sleep(0.5)
        self._flush()

        # Reset the adapter
        version = self._send_command("ATZ", delay=1.0)
        if "ELM" not in version and "elm" not in version.lower():
            raise ELM327Error(
                f"No ELM327 device detected on {self.port}. Got: {version}"
            )
        self._elm_version = version.strip()

        # Disable echo
        self._send_command("ATE0")
        # Disable line feeds
        self._send_command("ATL0")
        # Disable spaces in responses (makes parsing easier)
        self._send_command("ATS0")
        # Set protocol to ISO 15765-4 CAN (11-bit ID, 500 kbps) - Protocol 6
        resp = self._send_command("ATSP6")
        if "OK" not in resp and "6" not in resp:
            # Try auto protocol
            self._send_command("ATSP0")
        # Set timeout to ~200ms (multiply by 4ms: 50 * 4 = 200ms)
        self._send_command("ATST50")
        # Allow long messages (for multi-frame ISO-TP)
        self._send_command("ATAL")
        # Set CAN auto-formatting on
        self._send_command("ATCAF1")

        return self._elm_version

    def disconnect(self):
        """Close the serial connection."""
        if self._serial and self._serial.is_open:
            try:
                self._send_command("ATZ", delay=0.5)
            except Exception:
                pass
            self._serial.close()
        self._serial = None

    def set_header(self, can_id: int):
        """
        Set the CAN transmit header (arbitration ID).
        For 11-bit CAN IDs used in standard OBD2.
        """
        header = f"ATSH{can_id:03X}"
        resp = self._send_command(header)
        if "OK" not in resp:
            raise ELM327Error(f"Failed to set header to 0x{can_id:03X}: {resp}")

    def set_receive_filter(self, can_id: int):
        """
        Set the CAN receive filter to only accept responses from a specific ECU.
        """
        # Set CAN receive address filter
        cmd = f"ATCRA{can_id:03X}"
        resp = self._send_command(cmd)
        if "OK" not in resp:
            # Some adapters use ATCF instead
            self._send_command(f"ATCF{can_id:03X}")
            self._send_command("ATCM7FF")

    def clear_receive_filter(self):
        """Remove any receive address filter."""
        self._send_command("ATAR")

    def send_raw(self, data: bytes, timeout: float | None = None) -> list[bytes]:
        """
        Send raw UDS data bytes through ISO-TP and receive response frames.
        
        The ELM327 handles ISO-TP framing automatically when ATCAF is enabled.
        Data is sent as hex string, response is returned as list of byte sequences.
        
        Args:
            data: The UDS service bytes to send.
            timeout: Optional override for response timeout.
            
        Returns:
            List of response byte arrays (one per response line from ELM327).
        """
        if not self._serial or not self._serial.is_open:
            raise ELM327Error("Not connected")

        hex_str = data.hex().upper()
        raw_response = self._send_command(hex_str, delay=0.3, timeout=timeout)

        if not raw_response:
            return []

        responses = []
        for line in raw_response.split("\r"):
            line = line.strip()
            if not line:
                continue
            # Skip known non-data responses
            if line in ("NO DATA", "?", "UNABLE TO CONNECT", "CAN ERROR",
                        "BUS INIT: ...ERROR", "BUS ERROR", "STOPPED"):
                continue
            if line.startswith("SEARCHING"):
                continue
            # Try to parse as hex bytes
            cleaned = line.replace(" ", "")
            try:
                response_bytes = bytes.fromhex(cleaned)
                responses.append(response_bytes)
            except ValueError:
                # Not hex data, skip
                continue

        return responses

    def send_and_receive(self, data: bytes, expected_response_id: int = 0,
                         timeout: float | None = None) -> bytes | None:
        """
        Send UDS request and return the first valid response payload.
        
        Handles ISO-TP multi-frame assembly via ELM327 automatic formatting.
        
        Args:
            data: UDS service request bytes.
            expected_response_id: Expected response CAN ID (for filtering).
            timeout: Response timeout override.
            
        Returns:
            Response payload bytes (without CAN ID prefix), or None if no response.
        """
        responses = self.send_raw(data, timeout=timeout)
        if not responses:
            return None
        # Return the first response (most cases are single-frame)
        return responses[0] if responses else None

    def _send_command(self, command: str, delay: float = 0.1,
                      timeout: float | None = None) -> str:
        """Send an AT command or data string and read the response."""
        if not self._serial or not self._serial.is_open:
            raise ELM327Error("Not connected")

        # Clear input buffer
        self._serial.reset_input_buffer()

        # Send command with carriage return
        self._serial.write(f"{command}\r".encode("ascii"))
        time.sleep(delay)

        # Read response until prompt '>'
        old_timeout = self._serial.timeout
        if timeout:
            self._serial.timeout = timeout

        response = ""
        start = time.time()
        max_wait = timeout or self.timeout
        while True:
            if self._serial.in_waiting:
                chunk = self._serial.read(self._serial.in_waiting).decode(
                    "ascii", errors="ignore"
                )
                response += chunk
                if ">" in response:
                    break
            elif time.time() - start > max_wait:
                break
            else:
                time.sleep(0.02)

        self._serial.timeout = old_timeout

        # Clean up response: remove echo, prompt, and extra whitespace
        response = response.replace(">", "").strip()
        # Remove the echoed command if present
        if response.upper().startswith(command.upper()):
            response = response[len(command):].strip()

        return response

    def _flush(self):
        """Flush serial buffers."""
        if self._serial:
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
