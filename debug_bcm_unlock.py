"""
Attempt to unlock BCM security access using KeyGenMkI algorithm
with known JLR/Ford keybag values.

Algorithm: 24-bit LFSR (Ford Common 14229 Security)
- 3-byte seed from ECU
- 5-byte secret key (per-ECU, from keybag)
- Produces 3-byte response key

If we find the right secret key, we unlock the BCM and can run routine 0x205E.
"""
import serial
import time

PORT = "COM3"
BAUD = 500000


def keygen_mk1(seed_bytes: bytes, secret: bytes) -> bytes:
    """
    Ford KeyGenMkI algorithm.
    Takes 3-byte seed and 5-byte secret, returns 3-byte key.
    
    This is a 24-bit LFSR with initial state 0xC541A9.
    """
    # Convert seed to 24-bit integer
    seed = (seed_bytes[0] << 16) | (seed_bytes[1] << 8) | seed_bytes[2]
    
    # Convert 5-byte secret to 40-bit integer for iteration
    secret_int = 0
    for b in secret:
        secret_int = (secret_int << 8) | b
    
    # LFSR initial state
    sknum = 0xC541A9
    
    # Mix seed through LFSR (32 iterations)
    for i in range(32):
        bit_seed = (seed >> i) & 1
        bit_lfsr = sknum & 1
        feedback = bit_seed ^ bit_lfsr
        sknum = ((feedback << 23) | (sknum >> 1)) & 0xFFFFFF
    
    # Mix secret through LFSR (40 iterations for 5-byte key)
    for j in range(40):
        bit_key = (secret_int >> j) & 1
        bit_lfsr = sknum & 1
        feedback = bit_key ^ bit_lfsr
        sknum = ((feedback << 23) | (sknum >> 1)) & 0xFFFFFF
    
    # Result is the 24-bit LFSR state
    return bytes([(sknum >> 16) & 0xFF, (sknum >> 8) & 0xFF, sknum & 0xFF])


# Known JLR/Ford keybag entries — top candidates for L494 BCM
# Ordered by probability. BCM will lock after ~3-5 attempts.
# Run script, if locked out, cycle ignition and run again (it continues from where it left off)
KEYBAG = [
    # Most likely for JLR BCM
    b"DIODE",  # Very common JLR BCM key
    b"COLIN",  # Common JLR key
    b"Bosch",  # BCM supplier (Bosch makes JLR BCMs)
    bytes([0x78, 0x77, 0x68, 0x6B, 0x53]),  # L319 RLM diagnostic key
    b"JAMES",  # Known JLR key
    # Second tier
    b"Rowan",  # Known JLR key
    b"HELLA",  # Lighting supplier
    b"DENSO",  # Supplier
    b"DELPHI"[:5],  # Supplier (truncated to 5)
    b"CONTI",  # Continental (supplier)
    b"VALEO",  # Lighting supplier
    b"ROVER",  # JLR/Land Rover
    b"LANDR",  # Land Rover
    bytes([0x77, 0x87, 0xA5, 0x86, 0xA3]),  # L319 RLM programming key
    b"LIGHT",  # Lighting function
]

# Trim any entries longer than 5 bytes
KEYBAG = [k[:5] for k in KEYBAG]


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
cmd("ATSH720")
cmd("ATCRA728")

print("TesterPresent:", cmd("3E00", 1.0))

# Enter programming session
print("Programming session:", cmd("1002", 1.0))
cmd("3E00", 0.3)

# Request seed
print("\nRequesting seed...")
seed_resp = cmd("2701", 0.5)
print(f"Seed response: {seed_resp}")

if not seed_resp.startswith("6701"):
    print("ERROR: Could not get seed. Aborting.")
    s.close()
    exit(1)

# Extract 3-byte seed
seed_hex = seed_resp[4:10]  # After "6701"
seed_bytes = bytes.fromhex(seed_hex)
print(f"Seed: {seed_hex} ({seed_bytes.hex().upper()})")

if seed_bytes == b'\x00\x00\x00':
    print("\n*** BCM is ALREADY UNLOCKED! Seed is all zeros. ***")
    print("Trying routine 0x205E now...")
    resp = cmd("3101205E", 0.5, wait=10)
    print(f"  0x205E response: {resp}")
    s.close()
    exit(0)

# Try each keybag entry
print(f"\nTrying {len(KEYBAG)} known keys against seed {seed_hex}...")
print("(Will stop after first NRC 0x36 = exceeded attempts)\n")

for i, secret in enumerate(KEYBAG):
    # Compute key
    computed_key = keygen_mk1(seed_bytes, secret)
    key_hex = computed_key.hex().upper()
    
    # We need a fresh seed for each attempt (ECU changes seed after each try)
    if i > 0:
        # Request new seed
        cmd("3E00", 0.2)
        seed_resp = cmd("2701", 0.3)
        if not seed_resp.startswith("6701"):
            if "7F2736" in seed_resp:
                print(f"\n  *** LOCKED OUT (exceeded attempts) after {i} tries ***")
                print("  Cycle ignition and wait before trying again.")
                break
            print(f"  Seed request failed: {seed_resp}")
            break
        seed_hex = seed_resp[4:10]
        seed_bytes = bytes.fromhex(seed_hex)
        computed_key = keygen_mk1(seed_bytes, secret)
        key_hex = computed_key.hex().upper()
    
    # Send key (service 0x27, sub-function 0x02)
    send_cmd = f"2702{key_hex}"
    resp = cmd(send_cmd, 0.3)
    
    secret_display = secret.decode("ascii", errors="replace").rstrip("\x00")
    
    if "6702" in resp:
        print(f"  *** SUCCESS! Key '{secret_display}' ({secret.hex()}) UNLOCKED the BCM! ***")
        print(f"  Response: {resp}")
        print(f"\n  Now trying routine 0x205E...")
        cmd("3E00", 0.3)
        r = cmd("3101205E", 0.5, wait=10)
        print(f"  0x205E response: {r}")
        if "7101" in r:
            print(f"\n  *** ROUTINE 0x205E EXECUTED SUCCESSFULLY! ***")
            print(f"  Turn off ignition, wait 10 seconds, turn on, test turn signal!")
        break
    elif "7F2735" in resp:
        # Invalid key — try next one
        print(f"  [{i+1}/{len(KEYBAG)}] '{secret_display}' ({secret.hex()}) — wrong key")
    elif "7F2736" in resp:
        print(f"\n  *** LOCKED OUT after {i+1} attempts ***")
        print("  Cycle ignition and wait ~10 seconds before trying again.")
        break
    elif "7F2724" in resp:
        # Request sequence error — need to request seed again
        print(f"  [{i+1}] Sequence error, re-requesting seed...")
    else:
        print(f"  [{i+1}] '{secret_display}' — unexpected: {resp}")

s.close()
print("\n=== Done ===")
