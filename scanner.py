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
