"""
Fast probe of BCM routine IDs — scans only the ranges where JLR
typically places routines. Takes ~5-10 minutes instead of hours.

Ranges scanned:
  0x0100 - 0x03FF  (standard diagnostic routines)
  0x1000 - 0x10FF  (test routines)
  0x2000 - 0x21FF  (extended routines — where 0x205E lives on other BCMs)
  0xDD00 - 0xDFFF  (manufacturer-specific)
  0xF000 - 0xF0FF  (system routines)
  0xFE00 - 0xFFFF  (reserved/special)
"""
import serial
import time
import sys

PORT = "COM3"
BAUD = 500000

s = serial.Serial(PORT, BAUD, timeout=5)
time.sleep(0.5)


def cmd(c, delay=0.15, wait=2):
    s.reset_input_buffer()
    s.write((c + "\r").encode("ascii"))
    time.sleep(delay)
    resp = b""
    start = time.time()
    while time.time() - start < wait:
        if s.in_waiting:
            resp += s.read(s.in_waiting)
            if b">" in resp:
                break
        time.sleep(0.05)
    text = resp.decode("ascii", errors="ignore").replace(">", "").strip()
    return text


def nrc_meaning(resp):
    if "7F3111" in resp:
        return "service not supported"
    elif "7F3112" in resp:
        return "sub-function not supported"
    elif "7F3113" in resp:
        return "incorrect msg length"
    elif "7F3122" in resp:
        return "conditions not correct"
    elif "7F3124" in resp:
        return "request sequence error"
    elif "7F3131" in resp:
        return "OUT OF RANGE"
    elif "7F3133" in resp:
        return "security access denied"
    elif "7F3172" in resp:
        return "general programming failure"
    elif "7F317F" in resp:
        return "not supported in session"
    elif "7F3178" in resp:
        return "response pending"
    elif "7101" in resp:
        return "*** POSITIVE RESPONSE ***"
    elif "NODATA" in resp:
        return "no response"
    return f"other: {resp}"


# Init
cmd("ATZ", 1.5)
cmd("ATE0")
cmd("ATL0")
cmd("ATS0")
cmd("ATSP6")
cmd("ATSTFA")
cmd("ATAL")
cmd("ATCAF1")

# Target BCM
cmd("ATSH720")
cmd("ATCRA728")

print("TesterPresent:", cmd("3E00", 1.0))
print("Extended session:", cmd("1003", 1.0))

# Define scan ranges
ranges = [
    (0x0100, 0x0400, "Standard routines (0x0100-0x03FF)"),
    (0x1000, 0x1100, "Test routines (0x1000-0x10FF)"),
    (0x2000, 0x2200, "Extended routines (0x2000-0x21FF)"),
    (0xDD00, 0xE000, "Manufacturer-specific (0xDD00-0xDFFF)"),
    (0xF000, 0xF100, "System routines (0xF000-0xF0FF)"),
    (0xFE00, 0x10000, "Reserved/special (0xFE00-0xFFFF)"),
]

total_ids = sum(end - start for start, end, _ in ranges)
print(f"\nScanning {total_ids} routine IDs across {len(ranges)} ranges...")
print("Showing only VALID routines (skipping 'Out of Range')\n")

found_routines = []
scanned = 0
last_keepalive = time.time()

for range_start, range_end, range_name in ranges:
    print(f"--- {range_name} ---")
    for rid in range(range_start, range_end):
        # Keep session alive
        if time.time() - last_keepalive > 20:
            cmd("3E00", 0.1)
            last_keepalive = time.time()

        hex_cmd = f"3101{rid:04X}"
        resp = cmd(hex_cmd, 0.12, wait=2)
        scanned += 1

        # Skip "out of range" and "no data"
        if "7F3131" in resp or not resp or "NODATA" in resp:
            pass
        else:
            meaning = nrc_meaning(resp)
            print(f"  0x{rid:04X}: {resp}  ({meaning})")
            found_routines.append((rid, resp, meaning))

        # Progress
        if rid % 64 == 0:
            pct = (scanned / total_ids) * 100
            sys.stdout.write(f"\r  Scanning 0x{rid:04X} ({pct:.0f}%)  ")
            sys.stdout.flush()

    print()

print(f"\n{'='*50}")
print(f"SUMMARY: {len(found_routines)} valid routine IDs found")
print(f"{'='*50}\n")
for rid, resp, meaning in found_routines:
    print(f"  0x{rid:04X}: {meaning}  [raw: {resp}]")

s.close()
print("\n=== Done ===")
