"""
Debug: Clear BCM DTCs and immediately re-read to verify.
"""
import serial
import time

PORT = "COM3"
BAUD = 500000

s = serial.Serial(PORT, BAUD, timeout=10)
time.sleep(0.5)


def cmd(c, delay=0.5, wait=15):
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
        time.sleep(0.1)
    text = resp.decode("ascii", errors="ignore").replace(">", "").strip()
    return text


# Init
print("=== Init ===")
cmd("ATZ", 1.5)
cmd("ATE0")
cmd("ATL0")
cmd("ATS0")
cmd("ATSP6")
cmd("ATSTFA")
cmd("ATAL")
cmd("ATCAF1")
print("Ready")

# Target BCM
print("\n=== Setup BCM ===")
cmd("ATSH720")
cmd("ATCRA728")

# Read DTCs BEFORE clear
print("\n=== DTCs BEFORE clear ===")
resp = cmd("1902FF", 2.0, wait=15)
print(f"  Response: [{resp}]")

# Extended session
print("\n=== Start Extended Session ===")
resp = cmd("1003", 1.0)
print(f"  Response: [{resp}]")

# Tester Present
cmd("3E00", 0.5)

# Clear - group 0xFFFFFF (all)
print("\n=== Clear All DTCs (14 FF FF FF) ===")
resp = cmd("14FFFFFF", 1.0, wait=30)
print(f"  Response: [{resp}]")

# Wait for BCM to process
print("\n  Waiting 5 seconds...")
time.sleep(5)

# Tester Present to keep session
cmd("3E00", 0.5)

# Read DTCs AFTER clear
print("\n=== DTCs AFTER clear ===")
resp = cmd("1902FF", 2.0, wait=15)
print(f"  Response: [{resp}]")

# Also try reading with different status masks
print("\n=== DTCs status mask 0x09 (active+confirmed only) ===")
resp = cmd("190209", 2.0, wait=15)
print(f"  Response: [{resp}]")

print("\n=== DTCs status mask 0x08 (confirmed only) ===")
resp = cmd("190208", 2.0, wait=15)
print(f"  Response: [{resp}]")

s.close()
print("\n=== Done ===")
