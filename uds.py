"""
UDS (Unified Diagnostic Services) protocol implementation.

Implements ISO 14229 diagnostic services relevant to reading and clearing DTCs,
reading ECU identification, and managing diagnostic sessions.

This layer sits on top of the ELM327 transport and provides high-level
diagnostic operations.
"""

from dataclasses import dataclass, field
from enum import IntEnum

from elm327 import ELM327, ELM327Error


# --- UDS Service IDs (ISO 14229) ---

class UDSService(IntEnum):
    """UDS Service Identifiers."""
    DIAGNOSTIC_SESSION_CONTROL = 0x10
    ECU_RESET = 0x11
    CLEAR_DTC = 0x14
    READ_DTC_INFO = 0x19
    READ_DATA_BY_ID = 0x22
    SECURITY_ACCESS = 0x27
    COMMUNICATION_CONTROL = 0x28
    TESTER_PRESENT = 0x3E


class DiagnosticSession(IntEnum):
    """Diagnostic session types."""
    DEFAULT = 0x01
    PROGRAMMING = 0x02
    EXTENDED = 0x03


class DTCSubFunction(IntEnum):
    """Sub-functions for ReadDTCInformation (0x19)."""
    REPORT_NUMBER_OF_DTC = 0x01
    REPORT_DTC_BY_STATUS_MASK = 0x02
    REPORT_DTC_SNAPSHOT_ID = 0x03
    REPORT_DTC_SNAPSHOT_BY_DTC = 0x04
    REPORT_SUPPORTED_DTC = 0x0A


class DTCStatusBit(IntEnum):
    """DTC status mask bits."""
    TEST_FAILED = 0x01
    TEST_FAILED_THIS_CYCLE = 0x02
    PENDING = 0x04
    CONFIRMED = 0x08
    TEST_NOT_COMPLETED_SINCE_CLEAR = 0x10
    TEST_FAILED_SINCE_CLEAR = 0x20
    TEST_NOT_COMPLETED_THIS_CYCLE = 0x40
    WARNING_INDICATOR_REQUESTED = 0x80


class NegativeResponseCode(IntEnum):
    """UDS Negative Response Codes (NRC)."""
    GENERAL_REJECT = 0x10
    SERVICE_NOT_SUPPORTED = 0x11
    SUB_FUNCTION_NOT_SUPPORTED = 0x12
    INCORRECT_MSG_LENGTH = 0x13
    RESPONSE_TOO_LONG = 0x14
    BUSY_REPEAT_REQUEST = 0x21
    CONDITIONS_NOT_CORRECT = 0x22
    REQUEST_SEQUENCE_ERROR = 0x24
    REQUEST_OUT_OF_RANGE = 0x31
    SECURITY_ACCESS_DENIED = 0x33
    INVALID_KEY = 0x35
    EXCEEDED_NUMBER_OF_ATTEMPTS = 0x36
    UPLOAD_DOWNLOAD_NOT_ACCEPTED = 0x70
    TRANSFER_DATA_SUSPENDED = 0x71
    SERVICE_NOT_SUPPORTED_IN_SESSION = 0x7F


# --- Data Structures ---

@dataclass
class DTC:
    """Represents a single Diagnostic Trouble Code."""
    code: str  # e.g., "P0301", "U0100", "B1234", "C0035"
    raw_bytes: bytes  # The raw 3-byte DTC value
    status: int  # Status byte
    description: str = ""

    @property
    def is_active(self) -> bool:
        return bool(self.status & DTCStatusBit.TEST_FAILED)

    @property
    def is_confirmed(self) -> bool:
        return bool(self.status & DTCStatusBit.CONFIRMED)

    @property
    def is_pending(self) -> bool:
        return bool(self.status & DTCStatusBit.PENDING)

    @property
    def status_text(self) -> str:
        parts = []
        if self.is_active:
            parts.append("Active")
        if self.is_confirmed:
            parts.append("Confirmed")
        if self.is_pending:
            parts.append("Pending")
        if self.status & DTCStatusBit.WARNING_INDICATOR_REQUESTED:
            parts.append("MIL On")
        return ", ".join(parts) if parts else "Stored"


@dataclass
class ECUInfo:
    """ECU identification data."""
    part_number: str = ""
    software_version: str = ""
    hardware_version: str = ""
    serial_number: str = ""


@dataclass
class DiagResult:
    """Result of a diagnostic operation."""
    success: bool
    message: str = ""
    dtcs: list[DTC] = field(default_factory=list)
    ecu_info: ECUInfo | None = None
    raw_response: bytes = b""


# --- DTC Code Parsing ---

def parse_dtc_bytes(dtc_bytes: bytes) -> str:
    """
    Convert 3 raw DTC bytes into a human-readable code (e.g., P0301).
    
    DTC format (ISO 15031-6):
    - Byte 1, bits 7-6: Type (00=P, 01=C, 10=B, 11=U)
    - Byte 1, bits 5-4: Second digit
    - Byte 1, bits 3-0: Third digit
    - Byte 2, bits 7-4: Fourth digit
    - Byte 2, bits 3-0: Fifth digit
    """
    if len(dtc_bytes) < 2:
        return f"UNKNOWN({dtc_bytes.hex()})"

    first_byte = dtc_bytes[0]
    second_byte = dtc_bytes[1]

    # Type prefix from top 2 bits
    type_bits = (first_byte >> 6) & 0x03
    type_char = "PCBU"[type_bits]

    # Remaining digits
    digit2 = (first_byte >> 4) & 0x03
    digit3 = first_byte & 0x0F
    digit4 = (second_byte >> 4) & 0x0F
    digit5 = second_byte & 0x0F

    return f"{type_char}{digit2}{digit3:X}{digit4:X}{digit5:X}"


# --- UDS Client ---

class UDSClient:
    """
    UDS diagnostic client for communicating with vehicle ECUs.
    
    Uses an ELM327 adapter as the transport layer.
    """

    def __init__(self, elm: ELM327):
        self.elm = elm
        self._current_header: int | None = None

    def _setup_ecu(self, request_id: int, response_id: int):
        """Configure ELM327 to talk to a specific ECU."""
        if self._current_header != request_id:
            self.elm.set_header(request_id)
            self.elm.set_receive_filter(response_id)
            self._current_header = request_id

    def _send(self, request_id: int, response_id: int,
              data: bytes, timeout: float | None = None) -> bytes | None:
        """Send UDS request and return response."""
        self._setup_ecu(request_id, response_id)
        return self.elm.send_and_receive(data, response_id, timeout=timeout)

    def _is_positive_response(self, request_sid: int, response: bytes) -> bool:
        """Check if response is a positive response to our request."""
        if not response:
            return False
        # Positive response SID = request SID + 0x40
        return response[0] == (request_sid + 0x40)

    def _is_negative_response(self, response: bytes) -> tuple[bool, int]:
        """Check if response is a negative response. Returns (is_negative, NRC)."""
        if response and len(response) >= 3 and response[0] == 0x7F:
            return True, response[2]
        return False, 0

    def _get_nrc_text(self, nrc: int) -> str:
        """Get human-readable text for a Negative Response Code."""
        try:
            return NegativeResponseCode(nrc).name.replace("_", " ").title()
        except ValueError:
            return f"Unknown NRC (0x{nrc:02X})"

    # --- Diagnostic Session ---

    def start_diagnostic_session(self, request_id: int, response_id: int,
                                  session: DiagnosticSession = DiagnosticSession.EXTENDED
                                  ) -> DiagResult:
        """
        Start a diagnostic session with an ECU.
        Extended session is required for most non-standard operations.
        """
        data = bytes([UDSService.DIAGNOSTIC_SESSION_CONTROL, session])
        response = self._send(request_id, response_id, data)

        if response is None:
            return DiagResult(success=False, message="No response from ECU")

        if self._is_positive_response(UDSService.DIAGNOSTIC_SESSION_CONTROL, response):
            return DiagResult(success=True, message="Session started",
                              raw_response=response)

        is_neg, nrc = self._is_negative_response(response)
        if is_neg:
            return DiagResult(success=False,
                              message=f"Rejected: {self._get_nrc_text(nrc)}",
                              raw_response=response)

        return DiagResult(success=False, message="Unexpected response",
                          raw_response=response)

    def tester_present(self, request_id: int, response_id: int) -> bool:
        """Send TesterPresent to keep diagnostic session alive."""
        data = bytes([UDSService.TESTER_PRESENT, 0x00])
        response = self._send(request_id, response_id, data)
        return response is not None and self._is_positive_response(
            UDSService.TESTER_PRESENT, response
        )

    # --- Read DTCs ---

    def read_dtcs(self, request_id: int, response_id: int,
                  status_mask: int = 0xFF) -> DiagResult:
        """
        Read all DTCs from an ECU that match the given status mask.
        
        Default mask 0xFF returns all stored DTCs regardless of status.
        Use 0x09 for confirmed + active faults only.
        
        Args:
            request_id: ECU request CAN ID.
            response_id: ECU response CAN ID.
            status_mask: DTC status mask filter.
            
        Returns:
            DiagResult with list of DTCs found.
        """
        data = bytes([
            UDSService.READ_DTC_INFO,
            DTCSubFunction.REPORT_DTC_BY_STATUS_MASK,
            status_mask
        ])
        response = self._send(request_id, response_id, data, timeout=5.0)

        if response is None:
            return DiagResult(success=False, message="No response from ECU")

        is_neg, nrc = self._is_negative_response(response)
        if is_neg:
            return DiagResult(success=False,
                              message=f"Rejected: {self._get_nrc_text(nrc)}",
                              raw_response=response)

        if not self._is_positive_response(UDSService.READ_DTC_INFO, response):
            return DiagResult(success=False, message="Unexpected response",
                              raw_response=response)

        # Parse DTCs from response
        # Response format: [59] [sub-function] [status_availability] [DTC1_hi] [DTC1_lo] [DTC1_extra] [DTC1_status] ...
        dtcs = []
        if len(response) > 3:
            # DTC records start at byte index 3 (after SID+sub+availability)
            dtc_data = response[3:]
            # Each DTC record is 4 bytes: 3 bytes DTC + 1 byte status
            i = 0
            while i + 3 <= len(dtc_data):
                dtc_raw = dtc_data[i:i+3]
                dtc_status = dtc_data[i+3] if i + 3 < len(dtc_data) else 0
                
                # Skip empty/zero DTCs
                if dtc_raw != b'\x00\x00\x00':
                    code = parse_dtc_bytes(dtc_raw)
                    dtcs.append(DTC(
                        code=code,
                        raw_bytes=dtc_raw,
                        status=dtc_status,
                    ))
                i += 4

        if dtcs:
            msg = f"Found {len(dtcs)} DTC(s)"
        else:
            msg = "No DTCs stored"

        return DiagResult(success=True, message=msg, dtcs=dtcs,
                          raw_response=response)

    def get_dtc_count(self, request_id: int, response_id: int,
                      status_mask: int = 0xFF) -> DiagResult:
        """Get the number of DTCs matching the status mask."""
        data = bytes([
            UDSService.READ_DTC_INFO,
            DTCSubFunction.REPORT_NUMBER_OF_DTC,
            status_mask
        ])
        response = self._send(request_id, response_id, data)

        if response is None:
            return DiagResult(success=False, message="No response from ECU")

        if self._is_positive_response(UDSService.READ_DTC_INFO, response):
            if len(response) >= 6:
                count = (response[4] << 8) | response[5]
                return DiagResult(success=True,
                                  message=f"{count} DTC(s) stored",
                                  raw_response=response)
            return DiagResult(success=True, message="0 DTC(s) stored",
                              raw_response=response)

        is_neg, nrc = self._is_negative_response(response)
        if is_neg:
            return DiagResult(success=False,
                              message=f"Rejected: {self._get_nrc_text(nrc)}")

        return DiagResult(success=False, message="Unexpected response",
                          raw_response=response)

    # --- Clear DTCs ---

    def clear_dtcs(self, request_id: int, response_id: int,
                   group: int = 0xFFFFFF) -> DiagResult:
        """
        Clear/reset DTCs on an ECU.
        
        Args:
            request_id: ECU request CAN ID.
            response_id: ECU response CAN ID.
            group: DTC group to clear. 0xFFFFFF = all groups.
                   0xFFFF00 = all powertrain, etc.
                   
        Returns:
            DiagResult indicating success or failure.
        """
        # ClearDiagnosticInformation: [14] [group_hi] [group_mid] [group_lo]
        data = bytes([
            UDSService.CLEAR_DTC,
            (group >> 16) & 0xFF,
            (group >> 8) & 0xFF,
            group & 0xFF,
        ])
        response = self._send(request_id, response_id, data, timeout=5.0)

        if response is None:
            return DiagResult(success=False, message="No response from ECU")

        if self._is_positive_response(UDSService.CLEAR_DTC, response):
            return DiagResult(success=True, message="DTCs cleared successfully",
                              raw_response=response)

        is_neg, nrc = self._is_negative_response(response)
        if is_neg:
            msg = f"Clear failed: {self._get_nrc_text(nrc)}"
            if nrc == NegativeResponseCode.CONDITIONS_NOT_CORRECT:
                msg += " (try with ignition on, engine off)"
            return DiagResult(success=False, message=msg, raw_response=response)

        return DiagResult(success=False, message="Unexpected response",
                          raw_response=response)

    # --- ECU Identification ---

    def read_ecu_id(self, request_id: int, response_id: int) -> DiagResult:
        """
        Read ECU identification data (part number, software version, etc.).
        
        Uses ReadDataByIdentifier (0x22) with standard JLR DIDs.
        """
        ecu_info = ECUInfo()

        # Common Data Identifiers for JLR vehicles
        dids = {
            0xF187: "part_number",       # Vehicle Manufacturer ECU Hardware Number
            0xF189: "software_version",  # Vehicle Manufacturer ECU Software Version
            0xF191: "hardware_version",  # ECU Hardware Version Number
            0xF18C: "serial_number",     # ECU Serial Number
        }

        for did, field_name in dids.items():
            data = bytes([
                UDSService.READ_DATA_BY_ID,
                (did >> 8) & 0xFF,
                did & 0xFF,
            ])
            response = self._send(request_id, response_id, data)

            if response and self._is_positive_response(UDSService.READ_DATA_BY_ID,
                                                        response):
                # Response: [62] [DID_hi] [DID_lo] [data...]
                if len(response) > 3:
                    value_bytes = response[3:]
                    # Try to decode as ASCII, fall back to hex
                    try:
                        value = value_bytes.decode("ascii").strip("\x00").strip()
                    except (UnicodeDecodeError, ValueError):
                        value = value_bytes.hex().upper()
                    setattr(ecu_info, field_name, value)

        has_data = any([ecu_info.part_number, ecu_info.software_version,
                        ecu_info.hardware_version, ecu_info.serial_number])

        if has_data:
            return DiagResult(success=True, message="ECU info read",
                              ecu_info=ecu_info)
        else:
            return DiagResult(success=False,
                              message="Could not read ECU identification")

    # --- Routine Control ---

    def routine_control(self, request_id: int, response_id: int,
                        sub_function: int, routine_id: int,
                        option_record: bytes = b"") -> DiagResult:
        """
        Execute a Routine Control (0x31) command on an ECU.
        
        Args:
            request_id: ECU request CAN ID.
            response_id: ECU response CAN ID.
            sub_function: 0x01=Start, 0x02=Stop, 0x03=RequestResults
            routine_id: 2-byte routine identifier.
            option_record: Optional routine option data bytes.
            
        Returns:
            DiagResult indicating success or failure.
        """
        data = bytes([
            0x31,  # RoutineControl
            sub_function,
            (routine_id >> 8) & 0xFF,
            routine_id & 0xFF,
        ]) + option_record

        response = self._send(request_id, response_id, data, timeout=5.0)

        if response is None:
            return DiagResult(success=False, message="No response from ECU")

        if self._is_positive_response(0x31, response):
            return DiagResult(success=True, message="Routine executed successfully",
                              raw_response=response)

        is_neg, nrc = self._is_negative_response(response)
        if is_neg:
            msg = f"Routine rejected: {self._get_nrc_text(nrc)}"
            if nrc == NegativeResponseCode.SECURITY_ACCESS_DENIED:
                msg += " (security access required first)"
            elif nrc == NegativeResponseCode.CONDITIONS_NOT_CORRECT:
                msg += " (preconditions not met - check ignition state)"
            elif nrc == NegativeResponseCode.REQUEST_OUT_OF_RANGE:
                msg += " (routine ID not supported by this ECU)"
            return DiagResult(success=False, message=msg, raw_response=response)

        return DiagResult(success=False, message="Unexpected response",
                          raw_response=response)

    # --- Security Access ---

    def security_access_request_seed(self, request_id: int, response_id: int,
                                      access_level: int = 0x01) -> DiagResult:
        """
        Request a security seed from the ECU (step 1 of security access).
        
        Args:
            request_id: ECU request CAN ID.
            response_id: ECU response CAN ID.
            access_level: Security access level (odd number: 0x01, 0x03, etc.)
            
        Returns:
            DiagResult with raw_response containing the seed bytes.
        """
        data = bytes([UDSService.SECURITY_ACCESS, access_level])
        response = self._send(request_id, response_id, data, timeout=3.0)

        if response is None:
            return DiagResult(success=False, message="No response from ECU")

        if self._is_positive_response(UDSService.SECURITY_ACCESS, response):
            # Response: [67] [access_level] [seed bytes...]
            if len(response) > 2:
                seed = response[2:]
                if seed == b'\x00' * len(seed):
                    return DiagResult(success=True,
                                      message="Already unlocked (seed=0)",
                                      raw_response=response)
                return DiagResult(success=True,
                                  message=f"Seed received: {seed.hex().upper()}",
                                  raw_response=response)
            return DiagResult(success=True, message="Seed received",
                              raw_response=response)

        is_neg, nrc = self._is_negative_response(response)
        if is_neg:
            return DiagResult(success=False,
                              message=f"Security access denied: {self._get_nrc_text(nrc)}",
                              raw_response=response)

        return DiagResult(success=False, message="Unexpected response",
                          raw_response=response)

    def security_access_send_key(self, request_id: int, response_id: int,
                                  access_level: int, key: bytes) -> DiagResult:
        """
        Send a security key to the ECU (step 2 of security access).
        
        Args:
            request_id: ECU request CAN ID.
            response_id: ECU response CAN ID.
            access_level: Security access level + 1 (even number: 0x02, 0x04, etc.)
            key: Computed key bytes.
            
        Returns:
            DiagResult indicating if the ECU accepted the key.
        """
        data = bytes([UDSService.SECURITY_ACCESS, access_level]) + key
        response = self._send(request_id, response_id, data, timeout=3.0)

        if response is None:
            return DiagResult(success=False, message="No response from ECU")

        if self._is_positive_response(UDSService.SECURITY_ACCESS, response):
            return DiagResult(success=True, message="Security access granted",
                              raw_response=response)

        is_neg, nrc = self._is_negative_response(response)
        if is_neg:
            return DiagResult(success=False,
                              message=f"Key rejected: {self._get_nrc_text(nrc)}",
                              raw_response=response)

        return DiagResult(success=False, message="Unexpected response",
                          raw_response=response)

    # --- ECU Reset ---

    def ecu_reset(self, request_id: int, response_id: int,
                  reset_type: int = 0x01) -> DiagResult:
        """
        Request an ECU reset.
        
        Args:
            request_id: ECU request CAN ID.
            response_id: ECU response CAN ID.
            reset_type: 0x01=Hard reset, 0x02=Key off/on, 0x03=Soft reset
            
        Returns:
            DiagResult indicating success or failure.
        """
        data = bytes([UDSService.ECU_RESET, reset_type])
        response = self._send(request_id, response_id, data, timeout=5.0)

        if response is None:
            # Some ECUs reset immediately without responding
            return DiagResult(success=True,
                              message="Reset sent (no response - ECU may have restarted)")

        if self._is_positive_response(UDSService.ECU_RESET, response):
            return DiagResult(success=True, message="ECU reset successful",
                              raw_response=response)

        is_neg, nrc = self._is_negative_response(response)
        if is_neg:
            return DiagResult(success=False,
                              message=f"Reset rejected: {self._get_nrc_text(nrc)}",
                              raw_response=response)

        return DiagResult(success=False, message="Unexpected response",
                          raw_response=response)

    # --- Module Presence Check ---

    def ping_module(self, request_id: int, response_id: int) -> bool:
        """
        Check if a module is present and responding.
        Uses TesterPresent as a lightweight probe.
        """
        data = bytes([UDSService.TESTER_PRESENT, 0x00])
        response = self._send(request_id, response_id, data, timeout=2.0)
        if response and self._is_positive_response(UDSService.TESTER_PRESENT, response):
            return True
        # Some modules respond to default session control
        data = bytes([UDSService.DIAGNOSTIC_SESSION_CONTROL, DiagnosticSession.DEFAULT])
        response = self._send(request_id, response_id, data, timeout=2.0)
        return response is not None and self._is_positive_response(
            UDSService.DIAGNOSTIC_SESSION_CONTROL, response
        )
