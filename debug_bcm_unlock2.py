"""
BCM Security Unlock — using the CORRECT KeyGenMkI algorithm from
jakka351/Ford-ECU-Bruteforcer source code.

Key for CAN 0x720 level 0x01 is COLIN (0x434f4c494e) per the source comments.
Our first attempt failed because our LFSR implementation was wrong.
This version is a direct port of the C# code.
"""
import serial
import time

PORT = "COM3"
BAUD = 500000


def keygen_mk1(seed_int: int, sk0: int, sk1: int, sk2: int, sk3: int, sk4: int) -> int:
    """
    Direct port of the C# KeyGenMkI from Ford-ECU-Bruteforcer.
    seed_int: 24-bit seed as integer
    sk0-sk4: 5 secret key bytes
    Returns: 24-bit key as integer
    """
    # Reconstruct seed bytes
    sknum13 = (seed_int >> 16) & 0xFF
    b2 = (seed_int >> 8) & 0xFF
    b3 = seed_int & 0xFF

    sknum6 = (sknum13 << 16) + (b2 << 8) + b3
    sknum7 = ((sknum6 & 0xFF0000) >> 16) | (sknum6 & 0xFF00) | (sk0 << 24) | ((sknum6 & 0xFF) << 16)

    sknum8 = 0xC541A9

    # First loop: mix seed (32 iterations)
    for i in range(32):
        sknum10 = (((sknum7 >> i) & 1) ^ (sknum8 & 1)) << 23 | (sknum8 >> 1)
        sknum9 = sknum10

        sknum8 = (
            (sknum9 & 0xEF6FD7) |
            ((((sknum9 & 0x100000) >> 20) ^ ((sknum10 & 0x800000) >> 23)) << 20) |
            ((((sknum8 >> 1) & 0x8000) >> 15) ^ ((sknum10 & 0x800000) >> 23)) << 15 |
            ((((sknum8 >> 1) & 0x1000) >> 12) ^ ((sknum10 & 0x800000) >> 23)) << 12 |
            (32 * ((((sknum8 >> 1) & 0x20) >> 5) ^ ((sknum10 & 0x800000) >> 23))) |
            (8 * ((((sknum8 >> 1) & 8) >> 3) ^ ((sknum10 & 0x800000) >> 23)))
        )
        sknum8 &= 0xFFFFFF  # Keep 24-bit

    # Second loop: mix secret key (32 iterations)
    # Key arrangement: sk4 << 24 | sk3 << 16 | sk1 | sk2 << 8
    key_combined = (sk4 << 24) | (sk3 << 16) | sk1 | (sk2 << 8)

    for j in range(32):
        sknum12 = (((key_combined >> j) & 1) ^ (sknum8 & 1)) << 23 | (sknum8 >> 1)
        sknum11 = sknum12

        sknum8 = (
            (sknum11 & 0xEF6FD7) |
            ((((sknum11 & 0x100000) >> 20) ^ ((sknum12 & 0x800000) >> 23)) << 20) |
            ((((sknum8 >> 1) & 0x8000) >> 15) ^ ((sknum12 & 0x800000) >> 23)) << 15 |
            ((((sknum8 >> 1) & 0x1000) >> 12) ^ ((sknum12 & 0x800000) >> 23)) << 12 |
            (32 * ((((sknum8 >> 1) & 0x20) >> 5) ^ ((sknum12 & 0x800000) >> 23))) |
            (8 * ((((sknum8 >> 1) & 8) >> 3) ^ ((sknum12 & 0x800000) >> 23)))
        )
        sknum8 &= 0xFFFFFF

    # Final output transformation
    result = (
        ((sknum8 & 0xF0000) >> 16) |
        (16 * (sknum8 & 0xF)) |
        (((sknum8 & 0xF00000) >> 20) | ((sknum8 & 0xF000) >> 8)) << 8 |
        (((sknum8 & 0xFF0) >> 4) << 16)
    )
    return result & 0xFFFFFF


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


# Known keys for CAN ID 0x720 (BCM) from the source code
KEYS_0x720 = [
    ("COLIN", [0x43, 0x4F, 0x4C, 0x49, 0x4E]),  # Level 0x01
    ("0x40E234995F", [0x40, 0xE2, 0x34, 0x99, 0x5F]),  # Level 0x03
    ("0x0926F26388", [0x09, 0x26, 0xF2, 0x63, 0x88]),  # Level 0x11 (truncated to 5)
]

# Additional keybag from comments
EXTRA_KEYS = [
    ("Carol", [0x43, 0x61, 0x72, 0x6F, 0x6C]),
    ("JAMES", [0x4A, 0x41, 0x4D, 0x45, 0x53]),
    ("Flash", [0x46, 0x6C, 0x61, 0x73, 0x68]),
    ("FAITH", [0x46, 0x41, 0x49, 0x54, 0x48]),
    ("TAMER", [0x54, 0x41, 0x4D, 0x45, 0x52]),
    ("REMAT", [0x52, 0x45, 0x4D, 0x41, 0x54]),
    ("DIODE", [0x44, 0x49, 0x4F, 0x44, 0x45]),
    ("Rowan", [0x52, 0x6F, 0x77, 0x61, 0x6E]),
    ("LAURA", [0x4C, 0x41, 0x55, 0x52, 0x41]),
    ("JaMes", [0x4A, 0x61, 0x4D, 0x65, 0x73]),
    ("SAMMY", [0x53, 0x41, 0x4D, 0x4D, 0x59]),
    ("conti", [0x63, 0x6F, 0x6E, 0x74, 0x69]),
    ("Lupin", [0x4C, 0x75, 0x70, 0x69, 0x6E]),
    ("BOSEX", [0x42, 0x4F, 0x53, 0x45, 0x58]),
    ("nowaR", [0x6E, 0x6F, 0x77, 0x61, 0x52]),
    ("PANDA", [0x50, 0x41, 0x4E, 0x44, 0x41]),
    ("Jesus", [0x4A, 0x65, 0x73, 0x75, 0x73]),
    ("GANES", [0x47, 0x41, 0x4E, 0x45, 0x53]),
    ("Janis", [0x4A, 0x61, 0x6E, 0x69, 0x73]),
    ("BOSCH", [0x42, 0x4F, 0x53, 0x43, 0x48]),
    ("ARIAN", [0x41, 0x52, 0x49, 0x41, 0x4E]),
    ("DRIFT", [0x44, 0x52, 0x49, 0x46, 0x54]),
    ("BroWn", [0x42, 0x72, 0x6F, 0x57, 0x6E]),
    ("MACOM", [0x4D, 0x41, 0x43, 0x4F, 0x4D]),
    ("SKAND", [0x53, 0x4B, 0x41, 0x4E, 0x44]),
    ("Bosch", [0x42, 0x6F, 0x73, 0x63, 0x68]),
    ("BradW", [0x42, 0x72, 0x61, 0x64, 0x57]),  # From 0x727 RFA
]

s = serial.Serial(PORT, BAUD, timeout=5)
time.sleep(0.5)

# Init
cmd("ATZ", 1.5)
cmd("ATE0")
cmd("ATL0")
cmd("ATS0")
cmd("ATSP6")
cmd("ATSTFA")
cmd("ATAL")
cmd("ATCAF1")
cmd("ATSH720")
cmd("ATCRA728")

print("TesterPresent:", cmd("3E00", 1.0))
print("Programming session:", cmd("1002", 1.0))
cmd("3E00", 0.3)

# Try the known 0x720 key first (COLIN)
print("\n=== Trying known 0x720 keys ===")

all_keys = KEYS_0x720 + EXTRA_KEYS

for name, key_bytes in all_keys:
    cmd("3E00", 0.2)
    
    # Request seed
    seed_resp = cmd("2701", 0.3)
    if not seed_resp.startswith("6701"):
        print(f"  Seed request failed: {seed_resp}")
        if "7F2736" in seed_resp:
            print("  LOCKED OUT!")
            break
        continue
    
    seed_hex = seed_resp[4:10]
    seed_int = int(seed_hex, 16)
    
    if seed_int == 0:
        print("  *** ALREADY UNLOCKED! ***")
        break
    
    # Compute key using correct algorithm
    sk = key_bytes
    computed = keygen_mk1(seed_int, sk[0], sk[1], sk[2], sk[3], sk[4])
    key_hex = f"{computed:06X}"
    
    # Send key
    resp = cmd(f"2702{key_hex}", 0.3)
    
    if "6702" in resp:
        print(f"  *** SUCCESS! Key '{name}' unlocked the BCM! ***")
        print(f"  Seed: {seed_hex}, Computed key: {key_hex}")
        print(f"\n  Now executing routine 0x205E (Enable Protected Outputs)...")
        cmd("3E00", 0.3)
        r = cmd("3101205E", 1.0, wait=10)
        print(f"  Response: {r}")
        if "7101" in r:
            print(f"\n  *** SUCCESS! Protected outputs re-enabled! ***")
            print(f"  Turn ignition OFF, wait 10 seconds, turn ON, test turn signal!")
        elif "7F3131" in r:
            print(f"  Routine 0x205E still 'out of range' even after unlock.")
            print(f"  Trying 0x0205 with option 00...")
            r2 = cmd("3101020500", 0.5)
            print(f"  0x0205 response: {r2}")
        else:
            print(f"  Unexpected response: {r}")
        break
    elif "7F2735" in resp:
        print(f"  '{name}' — wrong key (seed: {seed_hex}, sent: {key_hex})")
    elif "7F2736" in resp:
        print(f"  LOCKED OUT after '{name}'!")
        break
    else:
        print(f"  '{name}' — response: {resp}")

s.close()
print("\n=== Done ===")
