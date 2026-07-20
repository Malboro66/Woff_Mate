import os
import sys
import re

HEX_DIGITS = set(b'0123456789ABCDEF')

def unscramble(raw: bytes) -> bytes:
    """Remove a camada de ofuscação hex+contador e devolve os bytes reais."""
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
    for t in tokens:
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

def find_strings(data: bytes, min_len: int = 4):
    """Acha sequências ASCII imprimíveis."""
    return [m.decode() for m in re.findall(rb'[\x20-\x7e]{%d,}' % min_len, data)]

if __name__ == '__main__':
    # FIX: Aceitar o caminho do ficheiro como argumento da linha de comando
    if len(sys.argv) < 2:
        print("Uso: python decode_dossier.py <caminho_para_o_ficheiro>")
        print('Exemplo: python decode_dossier.py "A:\\OBDSoftware\\WOFF\\...\\Pilot1Dossier.txt"')
        sys.exit(1)
        
    path = sys.argv[1]
    
    if not os.path.exists(path):
        print(f"[ERRO] Ficheiro não encontrado: {path}")
        sys.exit(1)
        
    with open(path, 'rb') as f:
        raw = f.read()
        
    data = unscramble(raw)

    print(f'{path}: {len(raw)} bytes ofuscados -> {len(data)} bytes reais\n')
    print(hexdump(data[:256]))
    print('...\n')
    print('Strings legiveis encontradas (len >= 4):')
    for s in find_strings(data):
        print(' ', s)