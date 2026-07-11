"""
Request security access seed from BCM.
This is step 1 of the 0x27 challenge — just asks for the seed, doesn't send a key.
Completely harmless — the BCM just gives us a random number.

Tries multiple access levels (0x01, 0x03, 0x05, etc.) since different levels
gate different functions.
"""
import serial
import time

PORT = "COM3"
BAUD = 500000

s = serial.Serial(PORT, BAUD, timeout=5)
time.sleep(0.5)


def cmd(c, delay=0.5, wait=5):
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

# Try in default session first
print("\n=== DEFAULT SESSION ===")
print("Session:", cmd("1001", 1.0))
cmd("3E00", 0.3)

print("\nRequesting seeds (service 0x27):")
for level in [0x01, 0x03, 0x05, 0x07, 0x09, 0x0B, 0x11, 0x13, 0x61, 0x63]:
    resp = cmd(f"27{level:02X}", 0.5)
    if "7F" in resp:
        # Decode NRC
        if "7F2712" in resp:
            nrc = "sub-function not supported"
        elif "7F2722" in resp:
            nrc = "conditions not correct"
        elif "7F2724" in resp:
            nrc = "request sequence error"
        elif "7F2735" in resp:
            nrc = "invalid key"
        elif "7F2736" in resp:
            nrc = "exceeded attempts (LOCKED OUT)"
        elif "7F277F" in resp:
            nrc = "not supported in active session"
        elif "7F2731" in resp:
            nrc = "request out of range"
        else:
            nrc = resp
        print(f"  Level 0x{level:02X}: REJECTED ({nrc})")
    elif "67" in resp:
        # Positive response: 67 [level] [seed bytes...]
        print(f"  Level 0x{level:02X}: SEED = {resp}")
        # Extract seed bytes
        if resp.startswith("67"):
            seed_hex = resp[4:]  # Skip "67" + level byte
            seed_len = len(seed_hex) // 2
            print(f"    Seed bytes ({seed_len} bytes): {seed_hex}")
            if seed_hex == "00" * seed_len:
                print(f"    *** ALREADY UNLOCKED (seed is all zeros) ***")
    else:
        print(f"  Level 0x{level:02X}: {resp}")

# Now try in programming session
print("\n=== PROGRAMMING SESSION ===")
print("Session:", cmd("1002", 1.0))
cmd("3E00", 0.3)

print("\nRequesting seeds:")
for level in [0x01, 0x03, 0x05, 0x07, 0x09, 0x0B, 0x11, 0x13, 0x61, 0x63]:
    resp = cmd(f"27{level:02X}", 0.5)
    if "7F" in resp:
        if "7F2712" in resp:
            nrc = "sub-function not supported"
        elif "7F2722" in resp:
            nrc = "conditions not correct"
        elif "7F2724" in resp:
            nrc = "request sequence error"
        elif "7F2735" in resp:
            nrc = "invalid key"
        elif "7F2736" in resp:
            nrc = "exceeded attempts (LOCKED OUT)"
        elif "7F277F" in resp:
            nrc = "not supported in active session"
        elif "7F2731" in resp:
            nrc = "request out of range"
        else:
            nrc = resp
        print(f"  Level 0x{level:02X}: REJECTED ({nrc})")
    elif "67" in resp:
        print(f"  Level 0x{level:02X}: SEED = {resp}")
        if resp.startswith("67"):
            seed_hex = resp[4:]
            seed_len = len(seed_hex) // 2
            print(f"    Seed bytes ({seed_len} bytes): {seed_hex}")
            if seed_hex == "00" * seed_len:
                print(f"    *** ALREADY UNLOCKED ***")
    else:
        print(f"  Level 0x{level:02X}: {resp}")

# Return to default
cmd("1001", 0.5)

s.close()
print("\n=== Done ===")
