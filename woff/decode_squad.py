import os
import sys

from woff.decode.common import unscramble

def hexdump(data: bytes, width: int = 16) -> str:
    """Hex dump clássico: offset | hex | ascii."""
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i:i + width]
        hex_part = ' '.join(f'{b:02X}' for b in chunk)
        ascii_part = ''.join(chr(b) if 0x20 <= b <= 0x7E else '.' for b in chunk)
        lines.append(f'{i:06X}  {hex_part:<{width * 3}}  {ascii_part}')
    return '\n'.join(lines)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Uso: python decode_squad.py <caminho_para_o_ficheiro>")
        print('Exemplo: python decode_squad.py "A:\\OBDSoftware\\WOFF\\...\\Scratchpad\\Esc 15.txt"')
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