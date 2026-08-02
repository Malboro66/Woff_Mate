"""Shared helpers for decoding obfuscated WoFF text files."""

HEX_DIGITS = set(b"0123456789ABCDEF")


def unscramble(raw: bytes) -> bytes:
    """Remove the WoFF hex+counter obfuscation layer and return real bytes."""
    tokens = []
    current = bytearray()
    for b in raw:
        if b in (0x0D, 0x0A):
            continue
        if b in HEX_DIGITS:
            current.append(b)
        else:
            tokens.append(bytes(current))
            current = bytearray()
    if current:
        tokens.append(bytes(current))

    decoded = bytearray()
    for token in tokens:
        decoded.append(int(token, 16) if token else 0)
    return bytes(decoded)
