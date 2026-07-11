# Debug Scripts

Standalone scripts for raw ELM327/UDS testing. Run directly with `python <script>.py`.  
All use COM3 at 500000 baud.

## General Diagnostics

| Script | Description | Time |
|--------|-------------|------|
| `debug_scan.py` | Raw ELM327 test — sends TesterPresent, session control, and DTC read to PCM and BCM with headers ON to see raw CAN frames | ~10s |
| `debug_scan2.py` | Same tests but with headers OFF / spaces OFF (matching main tool settings) to see how multi-frame responses appear to our parser | ~15s |

## BCM Clear / DTC Testing

| Script | Description | Time |
|--------|-------------|------|
| `debug_bcm_clear.py` | Sends a DTC clear command to BCM manually and watches the raw response — used to diagnose the NRC 0x78 (Response Pending) issue | ~30s |
| `debug_bcm_clear2.py` | Reads BCM DTCs before and after clearing — confirms whether codes actually disappear or come back immediately | ~30s |

## BCM Identification & Routine Probing

| Script | Description | Time |
|--------|-------------|------|
| `debug_bcm_id.py` | Tries multiple DIDs to identify BCM part/software number, then probes a short list of common routine IDs to find which ones the BCM recognizes | ~30s |
| `debug_bcm_routine.py` | Tries routine 0x0205 and 0x0202 with different option byte payloads to find the correct message format (since 0x0205 returned "incorrect length") | ~30s |
| `debug_bcm_probe_fast.py` | Scans likely JLR routine ID ranges (0x0100–0x03FF, 0x1000–0x10FF, 0x2000–0x21FF, 0xDD00–0xDFFF, 0xF000–0xF0FF, 0xFE00–0xFFFF) — finds valid routines without the multi-hour wait | ~5-10 min |
| `debug_bcm_probe_all.py` | Brute-force scans ALL 65,536 routine IDs (0x0000–0xFFFF) to find every routine the BCM supports | ~4-5 hours |

## What to run next

1. `python debug_bcm_probe_fast.py` — find all valid routines in common ranges (quick)
2. `python debug_bcm_routine.py` — find the right payload format for 0x0205
3. `python debug_bcm_probe_all.py` — full scan if fast probe misses something (overnight)
