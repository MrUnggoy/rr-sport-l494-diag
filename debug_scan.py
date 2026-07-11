"""
Raw debug script - send UDS commands manually and print raw ELM327 responses.
This bypasses all our abstraction to see exactly what's happening.
"""
import serial
import time

PORT = "COM3"
BAUD = 500000

s = serial.Serial(PORT, BAUD, timeout=5)
time.sleep(0.5)


def cmd(c, delay=0.5):
    """Send command, return raw response string."""
    s.reset_input_buffer()
    s.write((c + "\r").encode("ascii"))
    time.sleep(delay)
    # Read until we get the '>' prompt
    resp = b""
    start = time.time()
    while time.time() - start < 5:
        if s.in_waiting:
            resp += s.read(s.in_waiting)
            if b">" in resp:
                break
        time.sleep(0.05)
    text = resp.decode("ascii", errors="ignore").replace(">", "").strip()
    return text


# Initialize
print("=== ELM327 Init ===")
print("ATZ:", cmd("ATZ", 1.0))
print("ATE0:", cmd("ATE0"))
print("ATL0:", cmd("ATL0"))
print("ATS1:", cmd("ATS1"))  # Spaces ON so we can read it
print("ATH1:", cmd("ATH1"))  # Headers ON so we see CAN IDs
print("ATSP6:", cmd("ATSP6"))  # Protocol 6 = ISO 15765-4 CAN 500k
print("ATSTFA:", cmd("ATSTFA"))  # Timeout 1s
print("ATAL:", cmd("ATAL"))
print("ATCAF1:", cmd("ATCAF1"))

# === Test PCM (0x7E0 / 0x7E8) ===
print("\n=== PCM (0x7E0 -> 0x7E8) ===")
print("ATSH7E0:", cmd("ATSH7E0"))
print("ATCRA7E8:", cmd("ATCRA7E8"))

print("\n-- TesterPresent (3E 00) --")
print(cmd("3E00", 1.0))

print("\n-- DiagSession Default (10 01) --")
print(cmd("1001", 1.0))

print("\n-- ReadDTC by status mask (19 02 FF) --")
print(cmd("1902FF", 2.0))

# === Test BCM (0x720 / 0x728) ===
print("\n=== BCM (0x720 -> 0x728) ===")
print("ATSH720:", cmd("ATSH720"))
print("ATCRA728:", cmd("ATCRA728"))

print("\n-- TesterPresent (3E 00) --")
print(cmd("3E00", 1.0))

print("\n-- DiagSession Default (10 01) --")
print(cmd("1001", 1.0))

print("\n-- ReadDTC by status mask (19 02 FF) --")
print(cmd("1902FF", 2.0))

# === Test with no filter (broadcast style) ===
print("\n=== PCM no filter ===")
print("ATSH7E0:", cmd("ATSH7E0"))
print("ATAR:", cmd("ATAR"))  # Remove filter

print("\n-- TesterPresent (3E 00) --")
print(cmd("3E00", 1.0))

print("\n-- ReadDTC by status mask (19 02 FF) --")
print(cmd("1902FF", 2.0))

s.close()
print("\n=== Done ===")
