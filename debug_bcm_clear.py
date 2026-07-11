"""
Debug: Manually clear BCM DTCs and watch the raw response.
Shows exactly what the ELM327 returns after the clear command.
"""
import serial
import time

PORT = "COM3"
BAUD = 500000

s = serial.Serial(PORT, BAUD, timeout=10)
time.sleep(0.5)


def cmd(c, delay=0.5, wait=10):
    """Send command, wait up to `wait` seconds for '>' prompt."""
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
print(cmd("ATZ", 1.5))
cmd("ATE0")
cmd("ATL0")
cmd("ATS0")
cmd("ATSP6")
cmd("ATSTFA")
cmd("ATAL")
cmd("ATCAF1")

# Target BCM
print("\n=== Setup BCM (0x720 -> 0x728) ===")
print("ATSH720:", cmd("ATSH720"))
print("ATCRA728:", cmd("ATCRA728"))

# Verify BCM responds
print("\n=== TesterPresent ===")
print("Response:", cmd("3E00", 1.0))

# Start extended session
print("\n=== Extended Session (10 03) ===")
print("Response:", cmd("1003", 1.0))

# Keep alive
print("\n=== Tester Present ===")
print("Response:", cmd("3E00", 0.5))

# Clear DTCs - wait up to 30 seconds for response
print("\n=== Clear DTCs (14 FF FF FF) - waiting up to 30s ===")
resp = cmd("14FFFFFF", 1.0, wait=30)
print(f"Response: [{resp}]")

# If we got 7F1478, the real response might still come
if "7F1478" in resp.replace(" ", ""):
    print("\nGot Response Pending (0x78), waiting for real response...")
    # Just wait and read whatever comes next
    start = time.time()
    while time.time() - start < 30:
        if s.in_waiting:
            extra = s.read(s.in_waiting).decode("ascii", errors="ignore")
            print(f"  Received: [{extra.strip()}]")
            if ">" in extra:
                break
        time.sleep(0.5)

# Re-scan to check
print("\n=== Re-read DTCs (19 02 FF) ===")
print("Response:", cmd("1902FF", 3.0, wait=15))

s.close()
print("\n=== Done ===")
