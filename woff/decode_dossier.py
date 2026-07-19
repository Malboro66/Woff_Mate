import os
import re

dossier_path = r"A:\OBDSoftware\WOFF\OBDWW1 Over Flanders Fields\campaigns\CampaignData\Pilots\Pilot1Dossier.txt"

with open(dossier_path, "rb") as f:
    raw_bytes = f.read()

# 1. Máquina de Estados para extrair os pares hexadecimais
hex_str = ""
state = 0  # 0: Espera Real 1, 1: Espera Real 2, 2: Espera Ruído

for byte in raw_bytes:
    # Se for quebra de linha (13 ou 10), ignora o byte E NÃO muda o estado!
    # Isto garante que o ritmo de 3 bytes não é quebrado pelas linhas do ficheiro.
    if byte in (13, 10):
        continue
        
    if state == 0:
        hex_str += chr(byte)
        state = 1
    elif state == 1:
        hex_str += chr(byte)
        state = 2
    elif state == 2:
        # Salta o byte de ruído
        state = 0

# 2. Limpar qualquer caractere não-hexadecimal que possa ter escapado (por segurança)
hex_str = re.sub(r'[^0-9A-Fa-f]', '', hex_str)

# 3. Converter a String Hexadecimal para Bytes Reais
try:
    real_bytes = bytes.fromhex(hex_str)
    
    print("\n--- ESTATÍSTICAS REAIS DO PILOTO (Bytes em Decimal) ---\n")
    # Imprime os primeiros 100 bytes em formato decimal
    stats = list(real_bytes[:100])
    print(stats)
    
    print("\n--- TEXTO DESCODIFICADO (se aplicável) ---")
    # Tenta imprimir como UTF-8 para ver se há texto legível (nomes, etc)
    print(real_bytes.decode("utf-8", errors="replace")[:500])
    
except Exception as e:
    print(f"\n[ERRO HEX] {e}")
    print("String hexadecimal extraída (primeiros 200 chars):")
    print(hex_str[:200])