"""
Debug script #2 - Uses same ELM327 settings as main code (ATH0, ATS0, ATCAF1)
to see what the parsed response actually looks like.
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
    resp = b""
    start = time.time()
    while time.time() - start < 10:
        if s.in_waiting:
            resp += s.read(s.in_waiting)
            if b">" in resp:
                break
        time.sleep(0.05)
    text = resp.decode("ascii", errors="ignore").replace(">", "").strip()
    return text


# Initialize - SAME settings as main code
print("=== ELM327 Init (same as main.py) ===")
print("ATZ:", cmd("ATZ", 1.5))
print("ATE0:", cmd("ATE0"))
print("ATL0:", cmd("ATL0"))
print("ATS0:", cmd("ATS0"))       # Spaces OFF (same as main)
print("ATSP6:", cmd("ATSP6"))
print("ATSTFA:", cmd("ATSTFA"))   # 1 second timeout
print("ATAL:", cmd("ATAL"))       # Allow Long messages
print("ATCAF1:", cmd("ATCAF1"))   # CAN Auto Formatting ON
# NOTE: NOT setting ATH1 - headers stay OFF (default after ATZ)

# === Test PCM ===
print("\n=== PCM (0x7E0 -> 0x7E8) ===")
print("ATSH7E0:", cmd("ATSH7E0"))
print("ATCRA7E8:", cmd("ATCRA7E8"))

print("\n-- TesterPresent (3E00) --")
resp = cmd("3E00", 1.0)
print(f"  Raw: [{resp}]")
print(f"  Bytes: {repr(resp)}")

print("\n-- DiagSession Default (1001) --")
resp = cmd("1001", 1.0)
print(f"  Raw: [{resp}]")

print("\n-- ReadDTC (1902FF) -- waiting 5s")
resp = cmd("1902FF", 3.0)
print(f"  Raw: [{resp}]")
print(f"  Lines:")
for line in resp.split("\r"):
    line = line.strip()
    if line:
        print(f"    [{line}]")

# === Test BCM ===
print("\n=== BCM (0x720 -> 0x728) ===")
print("ATSH720:", cmd("ATSH720"))
print("ATCRA728:", cmd("ATCRA728"))

print("\n-- TesterPresent (3E00) --")
resp = cmd("3E00", 1.0)
print(f"  Raw: [{resp}]")

print("\n-- DiagSession Default (1001) --")
resp = cmd("1001", 1.0)
print(f"  Raw: [{resp}]")

print("\n-- ReadDTC (1902FF) -- waiting 5s")
resp = cmd("1902FF", 3.0)
print(f"  Raw: [{resp}]")
print(f"  Lines:")
for line in resp.split("\r"):
    line = line.strip()
    if line:
        print(f"    [{line}]")

# === Also try standard OBD2 Mode 03 (read DTCs) for comparison ===
print("\n=== Standard OBD2 Mode 03 (broadcast) ===")
print("ATSH7DF:", cmd("ATSH7DF"))
print("ATAR:", cmd("ATAR"))
print("\n-- Mode 03 (show stored DTCs) --")
resp = cmd("03", 3.0)
print(f"  Raw: [{resp}]")
print(f"  Lines:")
for line in resp.split("\r"):
    line = line.strip()
    if line:
        print(f"    [{line}]")

s.close()
print("\n=== Done ===")
