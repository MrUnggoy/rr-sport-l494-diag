"""
Probe ALL routine IDs (0x0000 - 0xFFFF) on the BCM.
Skips any that return NRC 0x31 (Out of Range) since those don't exist.
Reports anything else — that means the routine ID is valid.

This will take a few minutes to scan the full range.
"""
import serial
import time
import sys

PORT = "COM3"
BAUD = 500000

s = serial.Serial(PORT, BAUD, timeout=5)
time.sleep(0.5)


def cmd(c, delay=0.3, wait=3):
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
    return f"unknown: {resp}"


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

print("\n=== Probing ALL routine IDs (0x0000 - 0xFFFF) ===")
print("  Skipping 'Out of Range' (0x31) — showing only VALID routines\n")

found_routines = []
total = 0x10000
checked = 0
last_keepalive = time.time()

for rid in range(0x0000, 0x10000):
    # Keep session alive every 30 seconds
    if time.time() - last_keepalive > 25:
        cmd("3E00", 0.1)
        last_keepalive = time.time()

    # Send routine control start (31 01 XX XX)
    hex_cmd = f"3101{rid:04X}"
    resp = cmd(hex_cmd, 0.15, wait=2)

    checked += 1

    # Skip "out of range" — routine doesn't exist
    if "7F3131" in resp:
        pass
    elif not resp or "NODATA" in resp:
        pass
    else:
        # This routine ID is recognized!
        meaning = nrc_meaning(resp)
        print(f"  0x{rid:04X}: {resp}  ({meaning})")
        found_routines.append((rid, resp, meaning))

    # Progress every 256 IDs
    if rid % 256 == 0:
        pct = (rid / total) * 100
        sys.stdout.write(f"\r  Progress: 0x{rid:04X} ({pct:.1f}%)  Found: {len(found_routines)}  ")
        sys.stdout.flush()

print(f"\r  Progress: 100.0%  Found: {len(found_routines)}              ")
print(f"\n=== SUMMARY: {len(found_routines)} valid routine IDs found ===\n")
for rid, resp, meaning in found_routines:
    print(f"  0x{rid:04X}: {meaning}")

s.close()
print("\n=== Done ===")
