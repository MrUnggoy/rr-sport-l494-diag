"""
Debug: Try routine 0x0205 with various option record lengths/values.
NRC 0x13 means wrong message length — we need to find the right payload.
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

# Verify
print("TesterPresent:", cmd("3E00", 1.0))

# Start extended session
print("Extended session:", cmd("1003", 1.0))
cmd("3E00", 0.3)

# Routine 0x0205 - try different payload lengths
# Base command: 31 01 02 05 (start routine, ID 0x0205)
# We need to figure out what option bytes it expects

print("\n=== Routine 0x0205 - trying different payloads ===")

payloads = [
    ("3101020500", "31 01 0205 + 1 byte (00)"),
    ("3101020501", "31 01 0205 + 1 byte (01)"),
    ("310102050000", "31 01 0205 + 2 bytes (00 00)"),
    ("310102050001", "31 01 0205 + 2 bytes (00 01)"),
    ("310102050100", "31 01 0205 + 2 bytes (01 00)"),
    ("310102050101", "31 01 0205 + 2 bytes (01 01)"),
    ("31010205FF", "31 01 0205 + 1 byte (FF)"),
    ("31010205FFFF", "31 01 0205 + 2 bytes (FF FF)"),
    ("31010205000000", "31 01 0205 + 3 bytes (00 00 00)"),
    ("31010205010000", "31 01 0205 + 3 bytes (01 00 00)"),
    ("31010205FFFFFF", "31 01 0205 + 3 bytes (FF FF FF)"),
    ("3101020500000000", "31 01 0205 + 4 bytes (00 00 00 00)"),
    ("31010205FF000000", "31 01 0205 + 4 bytes (FF 00 00 00)"),
]

for payload, desc in payloads:
    cmd("3E00", 0.2)  # Keep session alive
    resp = cmd(payload, 0.5, wait=5)
    nrc_desc = ""
    if "7F3113" in resp:
        nrc_desc = "(wrong length)"
    elif "7F3131" in resp:
        nrc_desc = "(out of range)"
    elif "7F3122" in resp:
        nrc_desc = "(conditions not correct)"
    elif "7F3133" in resp:
        nrc_desc = "(security access denied)"
    elif "7F3124" in resp:
        nrc_desc = "(request sequence error)"
    elif "7101" in resp:
        nrc_desc = "*** ACCEPTED! ***"
    print(f"  {desc}: {resp}  {nrc_desc}")

# Also try routine 0x0202 with security access context
print("\n=== Routine 0x0202 - trying payloads ===")
cmd("3E00", 0.3)

payloads_0202 = [
    ("31010202", "31 01 0202 (no options)"),
    ("3101020200", "31 01 0202 + 1 byte (00)"),
    ("3101020201", "31 01 0202 + 1 byte (01)"),
    ("310102020000", "31 01 0202 + 2 bytes (00 00)"),
    ("31010202FF", "31 01 0202 + 1 byte (FF)"),
    ("31010202FFFF", "31 01 0202 + 2 bytes (FF FF)"),
]

for payload, desc in payloads_0202:
    cmd("3E00", 0.2)
    resp = cmd(payload, 0.5, wait=5)
    nrc_desc = ""
    if "7F3113" in resp:
        nrc_desc = "(wrong length)"
    elif "7F3131" in resp:
        nrc_desc = "(out of range)"
    elif "7F3122" in resp:
        nrc_desc = "(conditions not correct)"
    elif "7F3133" in resp:
        nrc_desc = "(security access denied)"
    elif "7F3124" in resp:
        nrc_desc = "(request sequence error)"
    elif "7101" in resp:
        nrc_desc = "*** ACCEPTED! ***"
    print(f"  {desc}: {resp}  {nrc_desc}")

s.close()
print("\n=== Done ===")
