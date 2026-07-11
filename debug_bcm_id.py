"""
Debug: Try multiple DIDs to identify the BCM hardware/software.
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

# Verify comms
print("TesterPresent:", cmd("3E00", 1.0))

# Try various DIDs (ReadDataByIdentifier = 0x22)
dids = {
    0xF187: "ECU Hardware Number",
    0xF188: "ECU Software Number",
    0xF189: "ECU Software Version",
    0xF18A: "System Supplier ID",
    0xF18B: "ECU Manufacturing Date",
    0xF18C: "ECU Serial Number",
    0xF190: "VIN",
    0xF191: "Hardware Version",
    0xF193: "System Supplier ECU HW Number",
    0xF194: "System Supplier ECU SW Number",
    0xF195: "Exhaust Regulation",
    0xF1A0: "JLR Part Number",
    0xF1A2: "JLR Software Part Number",
    0xF1A4: "JLR Calibration Part Number",
    0xF111: "ECU Core Assembly Number",
    0xF100: "Boot Software ID",
    0xF101: "Application Software ID",
    0xF102: "Application Data ID",
    0xF110: "Module config",
    0xD100: "JLR Diag Variant",
    0xD101: "JLR Diag Version",
}

print("\n=== BCM Identification DIDs ===")
for did, name in dids.items():
    hex_did = f"22{did:04X}"
    resp = cmd(hex_did, 0.5, wait=3)
    if resp and "7F" not in resp[:4] and resp != "NODATA":
        # Try to decode as ASCII
        if resp.startswith("62"):
            data_hex = resp[6:]  # Skip 62 + DID bytes
            try:
                ascii_val = bytes.fromhex(data_hex).decode("ascii", errors="replace").strip("\x00").strip()
            except:
                ascii_val = data_hex
            print(f"  0x{did:04X} ({name}): {ascii_val}  [raw: {resp}]")
        else:
            print(f"  0x{did:04X} ({name}): [raw: {resp}]")

# Also try to list supported routines by probing common IDs
print("\n=== Probing routine IDs (0x31 01 XXXX) ===")
print("  Looking for routines that don't return 'Out of Range'...")

# Start extended session first
cmd("1003", 1.0)
cmd("3E00", 0.5)

routine_ids_to_try = [
    0x0203, 0x0205, 0x0300, 0x0301, 0x0400,
    0x1000, 0x1001, 0x2000, 0x2001, 0x205E,
    0xDD00, 0xDD01, 0xDE00, 0xDE01, 0xDF00,
    0xFF00, 0xFF01, 0x0100, 0x0101, 0x0200,
    0x0201, 0x0202, 0x0204, 0x0206, 0x0207,
    0x0208, 0x0209, 0x020A, 0x020B, 0x020C,
    0xF000, 0xF001, 0xF00F, 0xFE00, 0xFE01,
]

for rid in routine_ids_to_try:
    hex_cmd = f"3101{rid:04X}"
    resp = cmd(hex_cmd, 0.3, wait=2)
    if resp and "7F3131" not in resp:
        # Not "out of range" — this routine ID exists!
        print(f"  0x{rid:04X}: {resp}")
    # Keep session alive every few attempts
    if rid % 5 == 0:
        cmd("3E00", 0.2)

s.close()
print("\n=== Done ===")
