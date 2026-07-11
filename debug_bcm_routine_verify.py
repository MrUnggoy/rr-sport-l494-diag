"""
Verify if routine 0x0205 actually executed by:
1. Reading BCM DTCs before
2. Running the routine
3. Requesting routine results (sub-function 0x03)
4. Checking routine status (sub-function 0x03)
5. Reading BCM DTCs after
6. Comparing before/after

Also tries sub-function 0x02 (Stop Routine) to see if it's "running"
"""
import serial
import time

PORT = "COM3"
BAUD = 500000

s = serial.Serial(PORT, BAUD, timeout=5)
time.sleep(0.5)


def cmd(c, delay=0.5, wait=10):
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
print("Extended session:", cmd("1003", 1.0))
cmd("3E00", 0.3)

# Step 1: Read DTCs BEFORE
print("\n=== DTCs BEFORE routine ===")
dtc_before = cmd("1902FF", 2.0, wait=10)
print(f"  {dtc_before}")

# Step 2: Try requesting results for 0x0205 BEFORE running it
print("\n=== Routine 0x0205 - Request Results BEFORE start ===")
print("  Sub-func 0x03 (results):", cmd("31030205", 0.5))

cmd("3E00", 0.3)

# Step 3: Start routine 0x0205 with option byte 0x00
print("\n=== Routine 0x0205 - START (31 01 0205 00) ===")
start_resp = cmd("3101020500", 0.5)
print(f"  Response: {start_resp}")

# Decode the response
if "7101" in start_resp:
    print("  → Positive response received")
    # Extract the routine info byte(s) after the routine ID
    # Format: 71 01 0205 [routineInfo...]
    # Let's see what the last bytes mean
    if len(start_resp) > 8:
        info = start_resp[8:]
        print(f"  → Routine info bytes: {info}")
        # Common meanings:
        # 10 = routine finished successfully
        # 20 = routine in progress
        # 30 = routine stopped
        # 00 = routine not started
        try:
            info_val = int(info[:2], 16)
            if info_val == 0x10:
                print("  → Status: Routine completed successfully")
            elif info_val == 0x20:
                print("  → Status: Routine in progress")
            elif info_val == 0x30:
                print("  → Status: Routine stopped")
            elif info_val == 0x00:
                print("  → Status: Routine not started / no info")
            else:
                print(f"  → Status: Unknown (0x{info_val:02X})")
        except:
            pass
elif "7F31" in start_resp:
    print(f"  → REJECTED: {start_resp}")
else:
    print(f"  → Unexpected: {start_resp}")

time.sleep(1)
cmd("3E00", 0.3)

# Step 4: Request routine results AFTER
print("\n=== Routine 0x0205 - Request Results AFTER start ===")
print("  Sub-func 0x03 (results):", cmd("31030205", 0.5))
print("  Sub-func 0x03 + 00:", cmd("3103020500", 0.5))

cmd("3E00", 0.3)

# Step 5: Try Stop Routine
print("\n=== Routine 0x0205 - STOP (31 02 0205) ===")
print("  Response:", cmd("31020205", 0.5))
print("  + option 00:", cmd("3102020500", 0.5))

time.sleep(2)
cmd("3E00", 0.3)

# Step 6: Read DTCs AFTER
print("\n=== DTCs AFTER routine ===")
dtc_after = cmd("1902FF", 2.0, wait=10)
print(f"  {dtc_after}")

# Step 7: Compare
print("\n=== Comparison ===")
if dtc_before == dtc_after:
    print("  DTCs UNCHANGED — routine had no effect on fault memory")
else:
    print("  DTCs CHANGED!")
    print(f"  Before: {dtc_before}")
    print(f"  After:  {dtc_after}")

s.close()
print("\n=== Done ===")
