# Debug Scripts

Standalone scripts for raw ELM327/UDS testing. Run directly with `python <script>.py`.  
All use COM3 at 500000 baud.

| Script | Description |
|--------|-------------|
| `debug_scan.py` | Raw ELM327 test — sends TesterPresent, session control, and DTC read to PCM and BCM with headers ON to see raw CAN frames |
| `debug_scan2.py` | Same tests but with headers OFF / spaces OFF (matching main tool settings) to see how multi-frame responses appear to our parser |
| `debug_bcm_clear.py` | Sends a DTC clear command to BCM manually and watches the raw response — used to diagnose the NRC 0x78 (Response Pending) issue |
| `debug_bcm_clear2.py` | Reads BCM DTCs before and after clearing — confirms whether codes actually disappear or come back immediately |
| `debug_bcm_id.py` | Tries multiple DIDs to identify BCM part/software number, then probes a short list of common routine IDs to find which ones the BCM recognizes |
| `debug_bcm_routine.py` | Tries routine 0x0205 and 0x0202 with different option byte payloads to find the correct message format (since 0x0205 returned "incorrect length") |
| `debug_bcm_probe_all.py` | Brute-force scans ALL 65,536 routine IDs (0x0000–0xFFFF) to find every routine the BCM supports — takes a few minutes |

## What to run next

1. `python debug_bcm_probe_all.py` — find all valid routines (the big scan)
2. `python debug_bcm_routine.py` — find the right payload format for 0x0205
