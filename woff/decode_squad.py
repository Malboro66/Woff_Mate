import re

HEX_DIGITS = set(b'0123456789ABCDEF')

def unscramble(raw: bytes) -> bytes:
    """Remove a camada de ofuscação hex+contador e devolve os bytes reais."""
    tokens = []
    current = bytearray()
    for b in raw:
        if b in (0x0D, 0x0A):  # Ignora quebras de linha
            continue
        if b in HEX_DIGITS:
            current.append(b)
        else:
            # Byte fora do alfabeto hex = contador -> fecha o token atual
            tokens.append(bytes(current))
            current = bytearray()
    if current:
        tokens.append(bytes(current))
 
    decoded = bytearray()
    for t in tokens:
        # Se o token estiver vazio (contadores consecutivos), assume 0
        decoded.append(int(t, 16) if t else 0)
    return bytes(decoded)

def hexdump(data: bytes, width: int = 16) -> str:
    """Hex dump clássico: offset | hex | ascii."""
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i:i + width]
        hex_part = ' '.join(f'{b:02X}' for b in chunk)
        ascii_part = ''.join(chr(b) if 0x20 <= b <= 0x7E else '.' for b in chunk)
        lines.append(f'{i:06X}  {hex_part:<{width * 3}}  {ascii_part}')
    return '\n'.join(lines)

# Conteudo do ficheiro Esc 15.txt que partilhou
raw_data = b"""0\xA11D\xA2A\xA3D\xA422\xA53B\xA631\xA712\xA82D\xA91\xAA78\xAB7A\xAC7\xAD52\xAE29\xAF1B\xB036\xB126\xB221\xB31B\xB42B\xB534\xB650\xB76B\xB845\xB99\xBA5\xBB6D\xBC2D\xBD16\xBE27\xBF2F\xC08\xC130\xC224\xC31A\xC4E\xC554\xC61F\xC710\xC812\xC95A\xCAA\xCB4E\xCC51\xCD4C\xCE34\xCF13\xD08\xD111\xD270\xD360\xD466\xD54A\xD66C\xD7"""

# Decodificar
data = unscramble(raw_data)

print("\n--- FICHEIRO DESCODIFICADO (Hex Dump) ---\n")
print(hexdump(data))
print("\n--- FIM ---\n")