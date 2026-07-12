"""
High-level diagnostic scanner that orchestrates multi-module scanning.

Provides the business logic for scanning all modules, reading/clearing DTCs,
and presenting results in a structured way.
"""

from dataclasses import dataclass, field

from elm327 import ELM327


def _is_protection_dtc(code: str) -> bool:
    """
    Check if a DTC code is related to BCM solid-state driver protection.
    
    Known protection codes:
    - U1000-00: "Solid State Driver Protection Active - Driver Disabled" (newer models)
    - U3000-xx: Control module internal fault (often accompanies U1000)
    - B108E: Short circuit protection on specific output (2014 L494)
    - B1xxx: Body system short circuit codes (suffixes -11, -12, -14, -15)
    """
    if not code:
        return False
    # U1000 / U1xxx / U3xxx (newer platforms)
    if code.startswith("U1") or code.startswith("U3"):
        return True
    # B108E specifically (your 2014 L494)
    if "108E" in code.upper():
        return True
    # B1xxx codes with short-circuit related patterns
    if code.startswith("B1"):
        return True
    return False
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

    # --- BCM Protected Output Reset (Verified) ---

    # Routine ID 0x205E: "Enable Protected Outputs"
    # Source: JLR official DTC U1000-00 diagnostic procedure
    # Location in SDD/Pathfinder: BCM → ECU Functions → Enable Protected Outputs
    # Applies to: L494 14MY+, L405 14MY+, L538 14MY+, L550 15MY+, L462 17MY+, L560 18MY+
    BCM_ENABLE_PROTECTED_OUTPUTS_ROUTINE = 0x205E

    def reset_bcm_protected_outputs(self, log_callback=None) -> DiagResult:
        """
        Re-enable BCM protected outputs using verified routine ID 0x205E.
        
        This is the factory procedure documented in JLR DTC U1000-00 diagnosis:
        "To re-enable the output circuits, perform the routine -
         Enable Protected Outputs (205E)"
        
        Procedure:
        1. Verify BCM is online and identify it
        2. Read DTCs to confirm U1000-00 is present
        3. Start extended diagnostic session
        4. Execute Routine Control 0x31, Start (0x01), routine ID 0x205E
        5. Re-scan to verify U1000-00 cleared
        
        IMPORTANT: Fix the underlying short circuit FIRST. If the short persists,
        the BCM will immediately re-disable the output.
        
        Returns:
            DiagResult with full procedure log.
        """
        from modules import get_module_by_name
        import time

        bcm = get_module_by_name("BCM")
        if not bcm:
            return DiagResult(success=False, message="BCM module not defined")

        req_id = bcm.request_id
        res_id = bcm.response_id
        log_lines = []

        def log(msg: str):
            log_lines.append(msg)
            if log_callback:
                log_callback(msg)

        # Step 1: Verify BCM responds
        log(f"[1/6] Pinging BCM at 0x{req_id:03X}/0x{res_id:03X}...")
        if not self.uds.ping_module(req_id, res_id):
            log("  FAILED - BCM not responding")
            return DiagResult(success=False,
                              message="BCM not responding\n" + "\n".join(log_lines))
        log("  OK - BCM online")

        # Step 2: Identify BCM
        log("[2/6] Reading BCM identification...")
        info_result = self.uds.read_ecu_id(req_id, res_id)
        if info_result.success and info_result.ecu_info:
            info = info_result.ecu_info
            if info.part_number:
                log(f"  Part Number: {info.part_number}")
            if info.software_version:
                log(f"  Software:    {info.software_version}")
        else:
            log("  Could not read BCM identification (continuing anyway)")

        # Step 3: Read DTCs to confirm U1000 is present
        log("[3/6] Reading BCM fault codes...")
        # Start session for DTC read
        self.uds.start_diagnostic_session(req_id, res_id, DiagnosticSession.EXTENDED)
        self.uds.tester_present(req_id, res_id)

        dtc_result = self.uds.read_dtcs(req_id, res_id)
        has_u1000 = False
        if dtc_result.success:
            log(f"  Found {len(dtc_result.dtcs)} DTC(s):")
            for dtc in dtc_result.dtcs:
                marker = " ← TARGET" if _is_protection_dtc(dtc.code) else ""
                log(f"    {dtc.code} [{dtc.status_text}]{marker}")
                if _is_protection_dtc(dtc.code):
                    has_u1000 = True
            if not has_u1000:
                log("  WARNING: No U1xxx protection DTC found.")
                log("  The routine may still work, but the output may already be enabled.")
        else:
            log(f"  Could not read DTCs: {dtc_result.message}")
            log("  Proceeding anyway...")

        # Step 4: Start extended diagnostic session
        log("[4/7] Starting extended diagnostic session...")
        self.uds.tester_present(req_id, res_id)
        session_result = self.uds.start_diagnostic_session(
            req_id, res_id, DiagnosticSession.EXTENDED
        )
        if session_result.success:
            log("  Extended session active")
        else:
            log(f"  Session response: {session_result.message}")
            log("  Attempting routine anyway...")

        # Step 5: Security Access (if required)
        log("[5/7] Attempting routine 0x205E (Enable Protected Outputs)...")
        self.uds.tester_present(req_id, res_id)

        routine_result = self.uds.routine_control(
            req_id, res_id,
            sub_function=0x01,  # Start Routine
            routine_id=self.BCM_ENABLE_PROTECTED_OUTPUTS_ROUTINE,
        )

        # If routine was rejected with Security Access Denied, try unlocking
        if not routine_result.success and routine_result.raw_response:
            is_neg = (len(routine_result.raw_response) >= 3 and
                      routine_result.raw_response[0] == 0x7F)
            nrc = routine_result.raw_response[2] if is_neg else 0

            if nrc == 0x33:  # Security Access Denied
                log("  Routine requires security access - attempting unlock...")
                from security import compute_security_key, get_bcm_key

                bcm_key = get_bcm_key(0x01)
                if not bcm_key:
                    log("  ERROR: No BCM security key available")
                    return DiagResult(success=False,
                                      message="\n".join(log_lines))

                # Request seed
                seed_result = self.uds.security_access_request_seed(
                    req_id, res_id, access_level=0x01
                )
                if not seed_result.success:
                    log(f"  Seed request failed: {seed_result.message}")
                    return DiagResult(success=False,
                                      message="\n".join(log_lines))

                # Check if already unlocked (seed = 0)
                if "Already unlocked" in seed_result.message:
                    log("  BCM already unlocked (seed=0)")
                else:
                    # Extract seed bytes and compute key
                    seed_bytes = seed_result.raw_response[2:]  # After 67 01
                    log(f"  Seed received: {seed_bytes.hex().upper()}")

                    computed_key = compute_security_key(seed_bytes, bcm_key)
                    log(f"  Key computed:  {computed_key.hex().upper()}")

                    # Send key
                    key_result = self.uds.security_access_send_key(
                        req_id, res_id, access_level=0x02, key=computed_key
                    )
                    if key_result.success:
                        log("  Security access GRANTED!")
                    else:
                        log(f"  Security access FAILED: {key_result.message}")
                        log("  The key 'COLIN' may not be correct for this BCM version.")
                        log("  Try security level 0x03 or 0x11 if available.")
                        return DiagResult(success=False,
                                          message="\n".join(log_lines))

                # Retry the routine now that we're unlocked
                log("  Retrying routine 0x205E after security unlock...")
                self.uds.tester_present(req_id, res_id)
                routine_result = self.uds.routine_control(
                    req_id, res_id,
                    sub_function=0x01,
                    routine_id=self.BCM_ENABLE_PROTECTED_OUTPUTS_ROUTINE,
                )

        if routine_result.success:
            log(f"  SUCCESS - Routine accepted!")
            log(f"  Response: {routine_result.raw_response.hex().upper()}")
        else:
            log(f"  FAILED - {routine_result.message}")
            if routine_result.raw_response:
                log(f"  Raw response: {routine_result.raw_response.hex().upper()}")
            log("")
            log("  Possible reasons:")
            log("  - Security access (0x27) may be required first")
            log("  - BCM may need a specific session type")
            log("  - The short circuit may still be present")
            return DiagResult(success=False,
                              message="\n".join(log_lines),
                              raw_response=routine_result.raw_response or b"")

        # Step 6: Clear DTCs (per JLR procedure: routine, then clear, then self-test)
        log("[6/7] Clearing DTCs after routine...")
        self.uds.tester_present(req_id, res_id)
        clear_result = self.uds.clear_dtcs(req_id, res_id)
        if clear_result.success:
            log("  DTCs cleared")
        else:
            log(f"  DTC clear: {clear_result.message}")

        # Step 7: Wait and re-scan to verify
        log("[7/7] Waiting 3 seconds, then re-scanning BCM...")
        time.sleep(3)
        self.uds.tester_present(req_id, res_id)

        rescan_result = self.uds.read_dtcs(req_id, res_id)
        if rescan_result.success:
            u1_codes = [d for d in rescan_result.dtcs if _is_protection_dtc(d.code)]
            if u1_codes:
                log(f"  Protection DTCs still present ({len(u1_codes)}):")
                for dtc in u1_codes:
                    log(f"    {dtc.code} [{dtc.status_text}]")
                log("")
                log("  The routine executed but protection DTCs remain.")
                log("  Try: Turn ignition OFF for 30 seconds, then back ON.")
                log("  If still present, the short circuit may not be fully repaired.")
            else:
                log("  No U1xxx protection DTCs found - outputs should be re-enabled!")
                log("")
                log("  NEXT STEPS:")
                log("  1. Turn ignition OFF, wait 10 seconds, turn back ON")
                log("  2. Test the affected circuit (tail light, turn signal, etc.)")
                log("  3. Run for 30+ seconds to confirm no fault returns")
        else:
            log(f"  Re-scan failed: {rescan_result.message}")
            log("  Cycle ignition and re-check manually")

        log("")
        log("  Routine 0x205E completed.")
        return DiagResult(success=True,
                          message="\n".join(log_lines),
                          dtcs=rescan_result.dtcs if rescan_result.success else [])

    def bcm_protected_output_diagnostic(self, log_callback=None) -> DiagResult:
        """
        Investigate BCM protected output faults (U1000/U3000).
        
        This procedure does NOT blindly attempt routine controls. Instead it:
        1. Verifies BCM is online and identifies it (part number / SW version)
        2. Reads all BCM DTCs and checks for protection-related codes
        3. Reports findings so the user can make an informed decision
        4. Offers a standard DTC clear (0x14) ONLY — clearly labeled as such
        5. Re-scans after clear to check if the fault returns immediately
        
        For actual protected output re-enable via Routine Control (0x31),
        the correct routine ID must be determined from JLR service documentation
        or captured from an SDD/Pathfinder session for your specific BCM software.
        
        This tool can then execute that known routine — see execute_known_routine().
        
        Returns:
            DiagResult with detailed log of everything attempted and observed.
        """
        from modules import get_module_by_name
        import time

        bcm = get_module_by_name("BCM")
        if not bcm:
            return DiagResult(success=False, message="BCM module not defined")

        req_id = bcm.request_id
        res_id = bcm.response_id
        log_lines = []

        def log(msg: str):
            log_lines.append(msg)
            if log_callback:
                log_callback(msg)

        # --- Step 1: Verify BCM is online ---
        log(f"[1/5] Pinging BCM at 0x{req_id:03X}/0x{res_id:03X}...")
        if not self.uds.ping_module(req_id, res_id):
            log("  FAILED - BCM not responding")
            log("  Check: Ignition ON? Adapter connected? Correct CAN bus (HS)?")
            return DiagResult(
                success=False,
                message="BCM not responding\n" + "\n".join(log_lines)
            )
        log("  OK - BCM responding")

        # --- Step 2: Identify BCM ---
        log(f"[2/5] Reading BCM identification...")
        info_result = self.uds.read_ecu_id(req_id, res_id)
        if info_result.success and info_result.ecu_info:
            info = info_result.ecu_info
            if info.part_number:
                log(f"  Part Number: {info.part_number}")
            if info.software_version:
                log(f"  Software:    {info.software_version}")
            if info.hardware_version:
                log(f"  Hardware:    {info.hardware_version}")
            if not info.part_number and not info.software_version:
                log("  Could not read identification DIDs")
        else:
            log("  Could not read identification (some DIDs may not be supported)")

        # --- Step 3: Start extended session and read DTCs ---
        log(f"[3/5] Reading BCM fault codes...")
        session_result = self.uds.start_diagnostic_session(
            req_id, res_id, DiagnosticSession.EXTENDED
        )
        if session_result.success:
            log("  Extended diagnostic session active")
        else:
            log(f"  Extended session not available ({session_result.message})")
            log("  Proceeding in default session")

        dtc_result = self.uds.read_dtcs(req_id, res_id)
        protection_dtcs = []
        other_dtcs = []

        if dtc_result.success:
            for dtc in dtc_result.dtcs:
                # Protection-related DTCs: U1000, U3000, B108E, B1xxx
                if _is_protection_dtc(dtc.code):
                    protection_dtcs.append(dtc)
                else:
                    other_dtcs.append(dtc)

            log(f"  Total DTCs: {len(dtc_result.dtcs)}")
            if protection_dtcs:
                log(f"  Protection-related DTCs ({len(protection_dtcs)}):")
                for dtc in protection_dtcs:
                    log(f"    {dtc.code} [{dtc.status_text}] "
                        f"(raw: {dtc.raw_bytes.hex().upper()}, status: 0x{dtc.status:02X})")
            else:
                log("  No protection-related DTCs (U1xxx/U3xxx) found")
            if other_dtcs:
                log(f"  Other DTCs ({len(other_dtcs)}):")
                for dtc in other_dtcs:
                    log(f"    {dtc.code} [{dtc.status_text}] "
                        f"(raw: {dtc.raw_bytes.hex().upper()}, status: 0x{dtc.status:02X})")
        else:
            log(f"  Could not read DTCs: {dtc_result.message}")
            if dtc_result.raw_response:
                log(f"  Raw response: {dtc_result.raw_response.hex().upper()}")

        # --- Step 4: Assessment ---
        log(f"[4/5] Assessment:")
        if not protection_dtcs:
            log("  No U1000/U3000 protection DTCs found.")
            log("  The protected output issue may have already been resolved,")
            log("  or the BCM may store the protection state separately from DTCs.")
            log("")
            log("  Options:")
            log("  - Try cycling ignition OFF for 60 seconds, then back ON")
            log("  - Disconnect battery for 60 seconds (forces full BCM reboot)")
            log("  - If output still disabled, JLR SDD/Pathfinder is needed")
            return DiagResult(
                success=True,
                message="\n".join(log_lines),
                dtcs=dtc_result.dtcs if dtc_result.success else []
            )

        log("  Protection DTCs are present.")
        log("  A standard DTC clear (service 0x14) will be attempted.")
        log("  NOTE: This clears the fault code but may NOT re-enable the")
        log("  protected output. If the output remains disabled after clearing")
        log("  and cycling ignition, a specific Routine Control command is needed.")
        log("  That routine ID must come from JLR documentation or an SDD capture.")

        # --- Step 5: Clear DTCs and re-scan ---
        log(f"[5/5] Clearing DTCs and re-scanning...")

        # Keep session alive
        self.uds.tester_present(req_id, res_id)

        clear_result = self.uds.clear_dtcs(req_id, res_id)
        if clear_result.success:
            log("  DTC clear command accepted (positive response)")
        else:
            log(f"  DTC clear response: {clear_result.message}")
            if clear_result.raw_response:
                log(f"  Raw: {clear_result.raw_response.hex().upper()}")

        # Wait a moment, then re-scan
        time.sleep(2)
        self.uds.tester_present(req_id, res_id)

        log("  Re-scanning BCM for DTCs...")
        rescan_result = self.uds.read_dtcs(req_id, res_id)
        if rescan_result.success:
            rescan_protection = [d for d in rescan_result.dtcs
                                 if _is_protection_dtc(d.code)]
            if rescan_protection:
                log(f"  Protection DTCs STILL PRESENT after clear ({len(rescan_protection)}):")
                for dtc in rescan_protection:
                    log(f"    {dtc.code} [{dtc.status_text}]")
                log("")
                log("  CONCLUSION: Standard DTC clear did not resolve the protection.")
                log("  The BCM is actively maintaining the protected state.")
                log("  Next steps:")
                log("  - Verify the wiring fault is actually repaired")
                log("  - Try: ignition OFF 60s, then ON, then re-scan")
                log("  - Try: battery disconnect for 60s (full BCM reboot)")
                log("  - If still present: a Routine Control (0x31) with the correct")
                log("    routine ID is required. Capture this from JLR SDD/Pathfinder")
                log("    or provide it manually via this tool's routine execute function.")
            else:
                log("  Protection DTCs cleared successfully!")
                log("  Remaining DTCs after clear:")
                if rescan_result.dtcs:
                    for dtc in rescan_result.dtcs:
                        log(f"    {dtc.code} [{dtc.status_text}]")
                else:
                    log("    None")
                log("")
                log("  NEXT: Turn ignition OFF, wait 30 seconds, turn ON.")
                log("  Check if the affected output (lamp/signal) is working.")
                log("  If the fault returns on next scan, the wiring issue persists.")
        else:
            log(f"  Re-scan failed: {rescan_result.message}")

        overall_success = clear_result.success
        return DiagResult(
            success=overall_success,
            message="\n".join(log_lines),
            dtcs=rescan_result.dtcs if rescan_result.success else protection_dtcs
        )

    def execute_known_routine(self, module_name: str, routine_id: int,
                              sub_function: int = 0x01,
                              option_record: bytes = b"",
                              require_session: bool = True) -> DiagResult:
        """
        Execute a KNOWN routine ID on a module.
        
        Use this ONLY when you have the correct routine ID from JLR documentation,
        an SDD/Pathfinder CAN capture, or other verified source.
        
        Args:
            module_name: Short name of the target module (e.g., "BCM").
            routine_id: The verified 2-byte routine identifier.
            sub_function: 0x01=Start, 0x02=Stop, 0x03=RequestResults.
            option_record: Optional routine parameter bytes.
            require_session: Whether to enter extended session first.
            
        Returns:
            DiagResult with full response details.
        """
        from modules import get_module_by_name
        module = get_module_by_name(module_name)
        if not module:
            return DiagResult(success=False,
                              message=f"Unknown module: {module_name}")

        req_id = module.request_id
        res_id = module.response_id

        # Verify module responds
        if not self.uds.ping_module(req_id, res_id):
            return DiagResult(success=False, message=f"{module_name} not responding")

        # Start session if required
        if require_session:
            self.uds.start_diagnostic_session(
                req_id, res_id, DiagnosticSession.EXTENDED
            )
            self.uds.tester_present(req_id, res_id)

        # Execute routine
        result = self.uds.routine_control(
            req_id, res_id,
            sub_function=sub_function,
            routine_id=routine_id,
            option_record=option_record,
        )

        # Add context to the message
        if result.success:
            result.message = (
                f"Routine 0x{routine_id:04X} executed on {module_name}\n"
                f"  Response: {result.raw_response.hex().upper()}"
            )
        else:
            result.message = (
                f"Routine 0x{routine_id:04X} on {module_name}: {result.message}\n"
                f"  Raw response: {result.raw_response.hex().upper() if result.raw_response else 'none'}"
            )

        return result
