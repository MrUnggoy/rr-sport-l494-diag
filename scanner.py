"""
High-level diagnostic scanner that orchestrates multi-module scanning.

Provides the business logic for scanning all modules, reading/clearing DTCs,
and presenting results in a structured way.
"""

from dataclasses import dataclass, field

from elm327 import ELM327
from modules import ECUModule, MODULES
from uds import UDSClient, DiagResult, DTC, DiagnosticSession


@dataclass
class ModuleScanResult:
    """Result of scanning a single module."""
    module: ECUModule
    is_present: bool = False
    dtcs: list[DTC] = field(default_factory=list)
    error: str = ""
    ecu_part_number: str = ""
    ecu_software: str = ""


class DiagnosticScanner:
    """
    Multi-module diagnostic scanner for Range Rover Sport L494.
    
    Coordinates communication with all known ECU modules through
    the ELM327 adapter and UDS protocol stack.
    """

    def __init__(self, elm: ELM327):
        self.elm = elm
        self.uds = UDSClient(elm)
        self._online_modules: list[ECUModule] = []

    def discover_modules(self, progress_callback=None) -> list[ModuleScanResult]:
        """
        Ping all known modules to see which ones are online/responding.
        
        Args:
            progress_callback: Optional callable(module_name, index, total)
                               for progress reporting.
        
        Returns:
            List of ModuleScanResult for each module attempted.
        """
        results = []
        total = len(MODULES)
        self._online_modules = []

        for i, module in enumerate(MODULES):
            if progress_callback:
                progress_callback(module.short_name, i, total)

            result = ModuleScanResult(module=module)
            try:
                is_present = self.uds.ping_module(
                    module.request_id, module.response_id
                )
                result.is_present = is_present
                if is_present:
                    self._online_modules.append(module)
            except Exception as e:
                result.error = str(e)

            results.append(result)

        return results

    def scan_module_dtcs(self, module: ECUModule,
                         start_session: bool = True) -> ModuleScanResult:
        """
        Read DTCs from a single module.
        
        Args:
            module: The ECU module to scan.
            start_session: Whether to start an extended diagnostic session first.
            
        Returns:
            ModuleScanResult with DTCs found.
        """
        result = ModuleScanResult(module=module)

        try:
            # Check if module responds
            is_present = self.uds.ping_module(
                module.request_id, module.response_id
            )
            result.is_present = is_present

            if not is_present:
                result.error = "Module not responding"
                return result

            # Start extended session for full DTC access
            if start_session:
                session_result = self.uds.start_diagnostic_session(
                    module.request_id, module.response_id,
                    DiagnosticSession.EXTENDED
                )
                if not session_result.success:
                    # Try default session - some modules don't support extended
                    self.uds.start_diagnostic_session(
                        module.request_id, module.response_id,
                        DiagnosticSession.DEFAULT
                    )

            # Read DTCs
            dtc_result = self.uds.read_dtcs(
                module.request_id, module.response_id
            )

            if dtc_result.success:
                result.dtcs = dtc_result.dtcs
            else:
                result.error = dtc_result.message

        except Exception as e:
            result.error = str(e)

        return result

    def scan_all_modules(self, progress_callback=None) -> list[ModuleScanResult]:
        """
        Scan all known modules for DTCs.
        
        Args:
            progress_callback: Optional callable(module_name, index, total)
            
        Returns:
            List of scan results, one per module.
        """
        results = []
        modules_to_scan = self._online_modules if self._online_modules else MODULES
        total = len(modules_to_scan)

        for i, module in enumerate(modules_to_scan):
            if progress_callback:
                progress_callback(module.short_name, i, total)

            result = self.scan_module_dtcs(module)
            results.append(result)

        return results

    def clear_module_dtcs(self, module: ECUModule) -> DiagResult:
        """
        Clear all DTCs on a single module.
        
        Starts an extended diagnostic session first, as most ECUs require it
        for clearing codes.
        """
        # Start extended session
        session_result = self.uds.start_diagnostic_session(
            module.request_id, module.response_id,
            DiagnosticSession.EXTENDED
        )
        # Some modules clear in default session, so proceed regardless

        # Clear all DTCs
        return self.uds.clear_dtcs(module.request_id, module.response_id)

    def clear_all_dtcs(self, progress_callback=None) -> dict[str, DiagResult]:
        """
        Clear DTCs on all responding modules.
        
        Returns:
            Dictionary mapping module short_name to clear result.
        """
        results = {}
        modules_to_clear = self._online_modules if self._online_modules else MODULES
        total = len(modules_to_clear)

        for i, module in enumerate(modules_to_clear):
            if progress_callback:
                progress_callback(module.short_name, i, total)

            result = self.clear_module_dtcs(module)
            results[module.short_name] = result

        return results

    def read_module_info(self, module: ECUModule) -> ModuleScanResult:
        """Read ECU identification data from a module."""
        result = ModuleScanResult(module=module)

        try:
            is_present = self.uds.ping_module(
                module.request_id, module.response_id
            )
            result.is_present = is_present

            if not is_present:
                result.error = "Module not responding"
                return result

            info_result = self.uds.read_ecu_id(
                module.request_id, module.response_id
            )

            if info_result.success and info_result.ecu_info:
                result.ecu_part_number = info_result.ecu_info.part_number
                result.ecu_software = info_result.ecu_info.software_version

        except Exception as e:
            result.error = str(e)

        return result

    # --- BCM Protected Output Reset ---

    def reset_bcm_protected_outputs(self, progress_callback=None) -> DiagResult:
        """
        Attempt to reset BCM FET/solid-state driver protected outputs.
        
        When the BCM detects overcurrent on a lighting circuit (e.g. turn signal,
        headlamp), it disables the FET driver and sets U1000/U3000. A standard
        DTC clear (0x14) may not re-enable the output - you need either:
        
        1. A UDS routine control (0x31) to reset the protected outputs
        2. An ECU reset (0x11) after clearing DTCs
        3. An ignition cycle (sometimes sufficient on JLR)
        
        This function tries multiple approaches in sequence:
        - Extended session -> Clear DTCs -> ECU soft reset
        - Extended session -> Routine control with known JLR routine IDs
        - ECU hard reset as last resort
        
        IMPORTANT: Fix the underlying short/overcurrent BEFORE running this.
        If the fault condition still exists, the output will immediately trip again.
        
        Returns:
            DiagResult indicating overall success or what was attempted.
        """
        from modules import get_module_by_name
        bcm = get_module_by_name("BCM")
        if not bcm:
            return DiagResult(success=False, message="BCM module not defined")

        req_id = bcm.request_id
        res_id = bcm.response_id
        messages = []

        # Step 1: Check BCM is online
        if progress_callback:
            progress_callback("BCM", 0, 5)
        if not self.uds.ping_module(req_id, res_id):
            return DiagResult(success=False, message="BCM not responding")
        messages.append("BCM online")

        # Step 2: Start extended diagnostic session
        if progress_callback:
            progress_callback("Session", 1, 5)
        session_result = self.uds.start_diagnostic_session(
            req_id, res_id, DiagnosticSession.EXTENDED
        )
        if session_result.success:
            messages.append("Extended session started")
        else:
            messages.append(f"Extended session: {session_result.message}")
            # Try default session
            self.uds.start_diagnostic_session(
                req_id, res_id, DiagnosticSession.DEFAULT
            )

        # Step 3: Clear all DTCs first
        if progress_callback:
            progress_callback("Clear DTCs", 2, 5)
        clear_result = self.uds.clear_dtcs(req_id, res_id)
        if clear_result.success:
            messages.append("DTCs cleared")
        else:
            messages.append(f"DTC clear: {clear_result.message}")

        # Step 4: Try routine control with known JLR routine IDs for FET reset
        # These are commonly used routine identifiers for protected output reset
        # on JLR platforms. The exact ID varies by BCM software version.
        if progress_callback:
            progress_callback("Routine", 3, 5)
        
        known_routine_ids = [
            0x0203,  # Reset Protected Outputs (common on L494/L405)
            0x0204,  # Reset All Output Drivers
            0x0F06,  # Clear DM Lock (seen in JLR/BMW shared platforms)
            0xFF00,  # General reset routine
            0x0200,  # Output driver reset
        ]
        
        routine_success = False
        for routine_id in known_routine_ids:
            result = self.uds.routine_control(
                req_id, res_id,
                sub_function=0x01,  # Start routine
                routine_id=routine_id,
            )
            if result.success:
                messages.append(
                    f"Routine 0x{routine_id:04X} executed successfully"
                )
                routine_success = True
                break
            # If "request out of range" just try next one
            # If "security access denied" we note it and move on

        if not routine_success:
            messages.append("No known routine IDs accepted (this is common)")
            messages.append("Attempting ECU reset as alternative...")

        # Step 5: ECU soft reset to force re-initialization of outputs
        if progress_callback:
            progress_callback("Reset", 4, 5)
        
        # Re-establish session after routine attempts
        self.uds.start_diagnostic_session(
            req_id, res_id, DiagnosticSession.EXTENDED
        )
        
        reset_result = self.uds.ecu_reset(req_id, res_id, reset_type=0x03)  # Soft reset
        if reset_result.success:
            messages.append("BCM soft reset sent")
        else:
            messages.append(f"Soft reset: {reset_result.message}")
            # Try hard reset
            reset_result = self.uds.ecu_reset(req_id, res_id, reset_type=0x01)
            if reset_result.success:
                messages.append("BCM hard reset sent")
            else:
                messages.append(f"Hard reset: {reset_result.message}")

        # Summary
        overall_success = clear_result.success or routine_success or reset_result.success
        summary = "\n".join(f"  - {m}" for m in messages)
        
        if overall_success:
            final_msg = (
                f"BCM reset procedure completed:\n{summary}\n\n"
                f"  Turn ignition OFF, wait 30 seconds, then turn ON again.\n"
                f"  Check if the affected output (turn signal/lamp) is restored.\n"
                f"  If the fault returns immediately, the wiring issue persists."
            )
        else:
            final_msg = (
                f"BCM reset procedure attempted but may not have succeeded:\n{summary}\n\n"
                f"  Try: Turn ignition OFF, disconnect battery for 60 seconds,\n"
                f"  reconnect, and cycle ignition. This forces a full BCM reboot.\n"
                f"  If that fails, JLR SDD/Pathfinder is needed for the specific\n"
                f"  protected output reset routine."
            )

        return DiagResult(success=overall_success, message=final_msg)
