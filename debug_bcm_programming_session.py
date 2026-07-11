"""
Try routine 0x205E in programming session (0x02) instead of extended (0x03).
Some BCMs only expose certain routines in programming mode.

Also tries 0x0205 and 0x0202 in programming session for comparison.
"""
import serial
import time

PORT = "COM3"
BAUD = 500000

s = serial.Serial(PORT, BAUD, timeout=5)
time.sleep(0.5)


def cmd(c, delay=0.5, wait=10):
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

# === Try in DEFAULT session first (0x01) ===
print("\n=== DEFAULT SESSION (10 01) ===")
print("Session:", cmd("1001", 1.0))
cmd("3E00", 0.3)
print("  0x205E:", cmd("310101205E", 0.5))
print("  0x205E (no opt):", cmd("3101205E", 0.5))
cmd("3E00", 0.3)
print("  0x0205 + 00:", cmd("3101020500", 0.5))
print("  0x0202:", cmd("31010202", 0.5))

# === Try in EXTENDED session (0x03) ===
print("\n=== EXTENDED SESSION (10 03) ===")
print("Session:", cmd("1003", 1.0))
cmd("3E00", 0.3)
print("  0x205E:", cmd("310101205E", 0.5))
print("  0x205E (no opt):", cmd("3101205E", 0.5))
cmd("3E00", 0.3)
print("  0x0205 + 00:", cmd("3101020500", 0.5))
print("  0x0202:", cmd("31010202", 0.5))

# === Try in PROGRAMMING session (0x02) ===
print("\n=== PROGRAMMING SESSION (10 02) ===")
print("Session:", cmd("1002", 1.0))
cmd("3E00", 0.3)
print("  0x205E:", cmd("310101205E", 0.5))
print("  0x205E (no opt):", cmd("3101205E", 0.5))
cmd("3E00", 0.3)
print("  0x0205 + 00:", cmd("3101020500", 0.5))
print("  0x0202:", cmd("31010202", 0.5))

# === Try other JLR session types (some BCMs use 0x41, 0x60, 0x61) ===
print("\n=== JLR SPECIAL SESSIONS ===")
for session_id in [0x41, 0x60, 0x61, 0x62, 0x03, 0x40]:
    resp = cmd(f"10{session_id:02X}", 0.5)
    if "7F" not in resp:
        print(f"  Session 0x{session_id:02X}: {resp} — ACCEPTED")
        cmd("3E00", 0.3)
        r = cmd("3101205E", 0.5)
        print(f"    0x205E: {r}")
        r = cmd("3101020500", 0.5)
        print(f"    0x0205 + 00: {r}")
    else:
        print(f"  Session 0x{session_id:02X}: {resp}")

# Return to default session
cmd("1001", 0.5)

s.close()
print("\n=== Done ===")
