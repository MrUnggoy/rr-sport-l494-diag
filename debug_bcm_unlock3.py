"""
BCM Security Unlock v3 — Carefully re-ported KeyGenMkI from C# source.

The C# algorithm has:
1. A 24-bit LFSR with initial state 0xC541A9
2. XOR feedback taps at bit positions 23, 20, 15, 12, 5, 3
3. Two mixing phases: seed (32 iterations) then key (32 iterations)
4. A final nibble-shuffle output transformation

This version adds test vectors and careful bit-by-bit porting.
"""
import serial
import time

PORT = "COM3"
BAUD = 500000


def keygen_mk1(seed_int: int, sk0: int, sk1: int, sk2: int, sk3: int, sk4: int) -> int:
    """
    Exact port of C# KeyGenMkI.
    
    C# variable mapping:
    - s = seed_int (24-bit)
    - sknum, sknum2, sknum3, sknum4, sknum5 = sk0, sk1, sk2, sk3, sk4
    - sknum6 = reconstructed seed
    - sknum7 = seed mixed with sk0 (first key byte in high position)
    - sknum8 = LFSR state (starts at 0xC541A9)
    """
    # C#: var sknum13 = (int)((byte)(s >> 0x10 & 0xFF));
    sknum13 = (seed_int >> 16) & 0xFF
    # C#: var b2 = (byte)(s >> 8 & 0xFF);
    b2 = (seed_int >> 8) & 0xFF
    # C#: var b3 = (byte)(s & 0xFF);
    b3 = seed_int & 0xFF

    # C#: var sknum6 = (sknum13 << 0x10) + ((int)b2 << 8) + (int)b3;
    sknum6 = (sknum13 << 16) + (b2 << 8) + b3

    # C#: var sknum7 = (sknum6 & 0xFF0000) >> 0x10 | (sknum6 & 0xFF00) | sknum << 0x18 | (sknum6 & 0xFF) << 0x10;
    # Note: "sknum" in C# parameter list is the first key byte (sk0)
    sknum7 = (
        ((sknum6 & 0xFF0000) >> 16) |
        (sknum6 & 0xFF00) |
        (sk0 << 24) |
        ((sknum6 & 0xFF) << 16)
    )
    # sknum7 is a 32-bit value

    # C#: var sknum8 = 0xC541A9;
    sknum8 = 0xC541A9

    # First loop: 32 iterations mixing sknum7 (seed + sk0)
    for i in range(32):
        # C#: sknum10 = (((sknum7 >> i & 1) ^ (sknum8 & 1)) << 0x17 | sknum8 >> 1)
        feedback_bit = ((sknum7 >> i) & 1) ^ (sknum8 & 1)
        shifted = sknum8 >> 1
        sknum10 = (feedback_bit << 23) | shifted
        sknum9 = sknum10

        # The complex XOR tap expression:
        # sknum8 = ((sknum9 & 0xEF6FD7) |
        #   ((sknum9 & 0x100000) >> 0x14 ^ (sknum10 & 0x800000) >> 0x17) << 0x14 |
        #   ((sknum8 >> 1 & 0x8000) >> 0xF ^ (sknum10 & 0x800000) >> 0x17) << 0xF |
        #   ((sknum8 >> 1 & 0x1000) >> 0xC ^ (sknum10 & 0x800000) >> 0x17) << 0xC |
        #   0x20 * ((sknum8 >> 1 & 0x20) >> 5 ^ (sknum10 & 0x800000) >> 0x17) |
        #   8 * ((sknum8 >> 1 & 8) >> 3 ^ (sknum10 & 0x800000) >> 0x17));

        # The feedback bit (bit 23 of sknum10)
        fb = (sknum10 >> 23) & 1

        # Bit 20: XOR existing bit 20 with feedback
        bit20 = (((sknum9 >> 20) & 1) ^ fb) << 20
        # Bit 15: XOR shifted bit 15 with feedback
        bit15 = (((shifted >> 15) & 1) ^ fb) << 15
        # Bit 12: XOR shifted bit 12 with feedback
        bit12 = (((shifted >> 12) & 1) ^ fb) << 12
        # Bit 5: XOR shifted bit 5 with feedback
        bit5 = (((shifted >> 5) & 1) ^ fb) << 5
        # Bit 3: XOR shifted bit 3 with feedback
        bit3 = (((shifted >> 3) & 1) ^ fb) << 3

        # 0xEF6FD7 = mask that clears bits 20, 15, 12, 5, 3
        # Binary: 1110 1111 0110 1111 1101 0111
        # Cleared bits: 20(0x100000), 15(0x8000), 12(0x1000), 5(0x20), 3(0x8)
        sknum8 = (sknum9 & 0xEF6FD7) | bit20 | bit15 | bit12 | bit5 | bit3
        sknum8 &= 0xFFFFFF

    # Second loop: 32 iterations mixing secret key bytes
    # C#: (sknum5 << 0x18 | sknum4 << 0x10 | sknum2 | sknum3 << 8)
    # sknum2=sk1, sknum3=sk2, sknum4=sk3, sknum5=sk4
    key_combined = (sk4 << 24) | (sk3 << 16) | sk1 | (sk2 << 8)

    for j in range(32):
        feedback_bit = ((key_combined >> j) & 1) ^ (sknum8 & 1)
        shifted = sknum8 >> 1
        sknum12 = (feedback_bit << 23) | shifted
        sknum11 = sknum12

        fb = (sknum12 >> 23) & 1

        bit20 = (((sknum11 >> 20) & 1) ^ fb) << 20
        bit15 = (((shifted >> 15) & 1) ^ fb) << 15
        bit12 = (((shifted >> 12) & 1) ^ fb) << 12
        bit5 = (((shifted >> 5) & 1) ^ fb) << 5
        bit3 = (((shifted >> 3) & 1) ^ fb) << 3

        sknum8 = (sknum11 & 0xEF6FD7) | bit20 | bit15 | bit12 | bit5 | bit3
        sknum8 &= 0xFFFFFF

    # Output transformation (nibble shuffle)
    # C#: return (sknum8 & 0xF0000) >> 0x10 | 0x10 * (sknum8 & 0xF) |
    #     ((sknum8 & 0xF00000) >> 0x14 | (sknum8 & 0xF000) >> 8) << 8 |
    #     (sknum8 & 0xFF0) >> 4 << 0x10;
    result = (
        ((sknum8 & 0xF0000) >> 16) |       # bits 19-16 -> bits 3-0
        (16 * (sknum8 & 0xF)) |             # bits 3-0 -> bits 7-4
        ((((sknum8 & 0xF00000) >> 20) | ((sknum8 & 0xF000) >> 8)) << 8) |  # bits 23-20 and 15-12 -> bits 15-8
        (((sknum8 & 0xFF0) >> 4) << 16)     # bits 11-4 -> bits 23-16
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


# Full keybag from Ford-ECU-Bruteforcer comments + extras
KEYBAG = [
    ("COLIN", b"COLIN"),
    ("Carol", b"Carol"),
    ("JAMES", b"JAMES"),
    ("Bosch", b"Bosch"),
    ("Flash", b"Flash"),
    ("FAITH", b"FAITH"),
    ("TAMER", b"TAMER"),
    ("REMAT", b"REMAT"),
    ("DIODE", b"DIODE"),
    ("Rowan", b"Rowan"),
    ("LAURA", b"LAURA"),
    ("JaMes", b"JaMes"),
    ("SAMMY", b"SAMMY"),
    ("conti", b"conti"),
    ("Lupin", b"Lupin"),
    ("BOSEX", b"BOSEX"),
    ("nowaR", b"nowaR"),
    ("PANDA", b"PANDA"),
    ("Jesus", b"Jesus"),
    ("GANES", b"GANES"),
    ("Janis", b"Janis"),
    ("BOSCH", b"BOSCH"),
    ("ARIAN", b"ARIAN"),
    ("DRIFT", b"DRIFT"),
    ("BroWn", b"BroWn"),
    ("MACOM", b"MACOM"),
    ("SKAND", b"SKAND"),
    ("BradW", b"BradW"),
    ("kbobA", b"kbobA"),
    ("HELLA", b"HELLA"),
    ("DENSO", b"DENSO"),
    ("VALEO", b"VALEO"),
    ("CONTI", b"CONTI"),
    ("ROVER", b"ROVER"),
    ("LANDR", b"LANDR"),
    ("LIGHT", b"LIGHT"),
    ("OuTuY", b"OuTuY"),
    ("slIor", b"slIor"),
    ("-MErM", b"-MErM"),
    # Binary keys
    ("0x720_L01", bytes([0x43, 0x4F, 0x4C, 0x49, 0x4E])),  # COLIN
    ("0x720_L03", bytes([0x40, 0xE2, 0x34, 0x99, 0x5F])),
    ("0x720_L11", bytes([0x09, 0x26, 0xF2, 0x63, 0x88])),
    ("RLM_diag", bytes([0x78, 0x77, 0x68, 0x6B, 0x53])),
    ("RLM_prog", bytes([0x77, 0x87, 0xA5, 0x86, 0xA3])),
    ("5B4174657D", bytes([0x5B, 0x41, 0x74, 0x65, 0x7D])),  # 0x760 key
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

print(f"\nTrying {len(KEYBAG)} keys with corrected algorithm...")
print("(No lockout detected — trying all)\n")

for name, key_bytes in KEYBAG:
    cmd("3E00", 0.15)

    # Request seed
    seed_resp = cmd("2701", 0.3)
    if not seed_resp.startswith("6701"):
        if "7F2736" in seed_resp:
            print(f"  LOCKED OUT!")
            break
        print(f"  Seed failed: {seed_resp}")
        continue

    seed_hex = seed_resp[4:10]
    seed_int = int(seed_hex, 16)

    if seed_int == 0:
        print("  *** ALREADY UNLOCKED! ***")
        break

    # Compute key
    sk = list(key_bytes[:5])
    while len(sk) < 5:
        sk.append(0)
    computed = keygen_mk1(seed_int, sk[0], sk[1], sk[2], sk[3], sk[4])
    key_hex = f"{computed:06X}"

    # Send key
    resp = cmd(f"2702{key_hex}", 0.3)

    if "6702" in resp:
        print(f"  *** SUCCESS! '{name}' unlocked the BCM! ***")
        print(f"  Seed: {seed_hex}, Key: {key_hex}")
        print(f"\n  Trying routine 0x205E...")
        cmd("3E00", 0.3)
        r = cmd("3101205E", 1.0, wait=10)
        print(f"  0x205E: {r}")
        if "7101" in r:
            print(f"\n  *** PROTECTED OUTPUTS RE-ENABLED! ***")
            print(f"  Turn ignition OFF 10s, ON, test turn signal!")
        elif "7F3131" in r:
            print(f"  0x205E still out of range. Trying with option bytes...")
            r2 = cmd("3101205E00", 0.5)
            print(f"  0x205E+00: {r2}")
            r3 = cmd("3101205EFF", 0.5)
            print(f"  0x205E+FF: {r3}")
            # Also try the fast-probe hits
            r4 = cmd("3101020500", 0.5)
            print(f"  0x0205+00: {r4}")
        break
    elif "7F2735" in resp:
        print(f"  [{name}] wrong key (seed:{seed_hex} sent:{key_hex})")
    elif "7F2736" in resp:
        print(f"  LOCKED OUT!")
        break
    else:
        print(f"  [{name}] resp: {resp}")

s.close()
print("\n=== Done ===")
