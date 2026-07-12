"""
JLR/Ford Security Access Algorithm (KeyGenMkI).

Implements the FORD_COMMON_14229_SECURITY seed-to-key algorithm used by
JLR (Jaguar Land Rover) and Ford ECUs for UDS Security Access (service 0x27).

The algorithm is a 24-bit Linear Feedback Shift Register (LFSR) with specific
tap positions. It takes a 3-byte seed from the ECU and a 5-byte secret key,
and produces a 3-byte response key.

Source: Reverse-engineered from SecAlg.dll (JLR SDD) and publicly documented
in jakka351/Ford-ECU-Bruteforcer and TekOnline Discovery 3 CAN bus series.

Known BCM (0x720) keys for JLR L494/L405 platforms:
  Security Level 0x01: "COLIN" = [0x43, 0x4F, 0x4C, 0x49, 0x4E]
  Security Level 0x03: [0x40, 0xE2, 0x34, 0x99, 0x5F]
  Security Level 0x11: [0x09, 0x26, 0xF2, 0x63, 0x88]
"""


def keygen_mk1(seed: int, key_bytes: list[int]) -> int:
    """
    Ford/JLR KeyGenMkI algorithm.
    
    Computes the 3-byte security key response from a 3-byte seed
    and a 5-byte secret key.
    
    Args:
        seed: 3-byte seed as integer (e.g., 0xABCDEF from ECU response)
        key_bytes: 5-byte secret key as list of ints [k0, k1, k2, k3, k4]
        
    Returns:
        3-byte computed key as integer (send back to ECU)
    """
    assert len(key_bytes) == 5, "Key must be exactly 5 bytes"

    k0, k1, k2, k3, k4 = key_bytes

    # Extract seed bytes
    seed_hi = (seed >> 16) & 0xFF
    seed_mid = (seed >> 8) & 0xFF
    seed_lo = seed & 0xFF

    # Build sknum6 and sknum7
    sknum6 = (seed_hi << 16) + (seed_mid << 8) + seed_lo
    sknum7 = (
        ((sknum6 & 0xFF0000) >> 16) |
        (sknum6 & 0xFF00) |
        (k0 << 24) |
        ((sknum6 & 0xFF) << 16)
    )

    # LFSR initial state
    sknum8 = 0xC541A9

    # First pass: mix seed+key through LFSR (32 iterations)
    for i in range(32):
        feedback_bit = ((sknum7 >> i) & 1) ^ (sknum8 & 1)
        shifted = (feedback_bit << 23) | (sknum8 >> 1)

        # Apply tap XOR operations at specific positions
        bit23 = (shifted & 0x800000) >> 23
        sknum8 = (
            (shifted & 0xEF6FD7) |
            ((((shifted & 0x100000) >> 20) ^ bit23) << 20) |
            ((((sknum8 >> 1) & 0x8000) >> 15) ^ bit23) << 15 |
            ((((sknum8 >> 1) & 0x1000) >> 12) ^ bit23) << 12 |
            ((((sknum8 >> 1) & 0x20) >> 5) ^ bit23) << 5 |
            ((((sknum8 >> 1) & 0x8) >> 3) ^ bit23) << 3
        )

    # Build second pass input from remaining key bytes
    second_input = (k4 << 24) | (k3 << 16) | (k1) | (k2 << 8)

    # Second pass: mix remaining key through LFSR (32 iterations)
    for j in range(32):
        feedback_bit = ((second_input >> j) & 1) ^ (sknum8 & 1)
        shifted = (feedback_bit << 23) | (sknum8 >> 1)

        bit23 = (shifted & 0x800000) >> 23
        sknum8 = (
            (shifted & 0xEF6FD7) |
            ((((shifted & 0x100000) >> 20) ^ bit23) << 20) |
            ((((sknum8 >> 1) & 0x8000) >> 15) ^ bit23) << 15 |
            ((((sknum8 >> 1) & 0x1000) >> 12) ^ bit23) << 12 |
            ((((sknum8 >> 1) & 0x20) >> 5) ^ bit23) << 5 |
            ((((sknum8 >> 1) & 0x8) >> 3) ^ bit23) << 3
        )

    # Final output permutation
    result = (
        ((sknum8 & 0xF0000) >> 16) |
        (0x10 * (sknum8 & 0xF)) |
        ((((sknum8 & 0xF00000) >> 20) | ((sknum8 & 0xF000) >> 8)) << 8) |
        (((sknum8 & 0xFF0) >> 4) << 16)
    )

    return result & 0xFFFFFF


def compute_security_key(seed_bytes: bytes, secret_key: list[int]) -> bytes:
    """
    High-level helper: compute security response from seed bytes.
    
    Args:
        seed_bytes: 3-byte seed from ECU (from 0x67 0x01 response)
        secret_key: 5-byte secret key for the target ECU/level
        
    Returns:
        3-byte key to send back in 0x27 0x02 request
    """
    assert len(seed_bytes) >= 3, "Seed must be at least 3 bytes"
    seed_int = (seed_bytes[0] << 16) | (seed_bytes[1] << 8) | seed_bytes[2]
    
    if seed_int == 0:
        # Zero seed means already unlocked
        return b'\x00\x00\x00'
    
    result = keygen_mk1(seed_int, secret_key)
    return bytes([
        (result >> 16) & 0xFF,
        (result >> 8) & 0xFF,
        result & 0xFF,
    ])


# --- Known JLR Security Keys ---
# Format: {CAN_request_ID: {security_level: [k0, k1, k2, k3, k4]}}

JLR_SECURITY_KEYS = {
    # BCM (Body Control Module) - 0x720
    0x720: {
        0x01: [0x43, 0x4F, 0x4C, 0x49, 0x4E],  # "COLIN" - diagnostic access
        0x03: [0x40, 0xE2, 0x34, 0x99, 0x5F],  # programming access
        0x11: [0x09, 0x26, 0xF2, 0x63, 0x88],  # extended access
    },
}


def get_bcm_key(security_level: int = 0x01) -> list[int] | None:
    """Get the BCM security key for a given access level."""
    bcm_keys = JLR_SECURITY_KEYS.get(0x720, {})
    return bcm_keys.get(security_level)
