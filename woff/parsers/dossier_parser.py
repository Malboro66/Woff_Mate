#!/usr/bin/env python3
r"""
Parser de Dossier Binário (parsers/dossier_parser.py)
══════════════════════════════════════════════════════════════════
Faz a leitura e desencriptação do ficheiro Pilot{N}Dossier.txt.
Implementação baseada na engenharia reversa do código Java do 
Pilot Log Editor (JJJ65).

O WoFF ofusca este ficheiro com:
1. Pares hexadecimais intercalados com bytes de contador.
2. Cifra XOR usando uma chave gerada pelo nome do ficheiro.
3. Chave invertida a cada linha.
══════════════════════════════════════════════════════════════════
"""

import os
import logging
from datetime import datetime
from typing import Optional, List
from models import WoFFPilot, WoFFWingman, WoFFDecoration

log = logging.getLogger("WoFFWatch")

class WoFFDossierParser:
    def __init__(self):
        self.pilot: Optional[WoFFPilot] = None
        self.raw_strings: List[str] = []
        self.wingmen: List[WoFFWingman] = []
        self.decorations: List[WoFFDecoration] = []

    def _create_key(self, pName: str) -> str:
        """Gera a chave de cifra exatamente como o jogo faz (createkey)."""
        plainkey = "78CrztPRVzYQpYu90MnyW"
        
        # Soma dos valores ASCII do nome do ficheiro
        soucet = sum(ord(c) for c in pName)
        sum_val = soucet % 128
        
        pos = sum_val % 10
        if pos == 0: pos = 9
        
        length = sum_val % 12
        if length == 0: length = 4
        
        prekey = ""
        ind = pos
        for _ in range(length):
            prekey += plainkey[ind - 1]
            ind += 1
            
        postkey = ""
        in_val = pos
        lengt = length
        for _ in range(in_val):
            postkey += plainkey[lengt - 1]
            lengt += 1
            
        sp = chr(sum_val)
        return prekey + sp + plainkey + postkey

    def parse(self, path: str) -> bool:
        log.info(f"[BIN] Analisando Dossier: {os.path.basename(path)}")
        try:
            with open(path, "rb") as f:
                raw_lines = f.readlines()
        except Exception as e:
            log.error(f"  Falha ao ler {path}: {e}")
            return False

        fname = os.path.basename(path)
        pName = fname.replace(".txt", "")
        current_key = self._create_key(pName)
        
        player_data = []

        for raw_line in raw_lines:
            line = raw_line.decode("cp1252", errors="replace").strip()
            if not line:
                continue
                
            decoded_line = ""
            hex_buffer = ""
            key_index = 0
            
            for char in line:
                code = ord(char)
                if code > 71:  # Byte de contador/separador
                    if hex_buffer:
                        if len(hex_buffer) < 2:
                            hex_buffer = "0" + hex_buffer
                        try:
                            val = int(hex_buffer, 16)
                            key_char = ord(current_key[key_index])
                            fin_val = val ^ key_char  # Cifra XOR
                            decoded_line += chr(fin_val)
                        except ValueError:
                            pass # Ignora hex inválido
                        
                        key_index += 1
                        if key_index == len(current_key):
                            key_index = 0
                        hex_buffer = ""
                elif code != 32:  # Ignora espaços (32) que o Java força
                    hex_buffer += char
                    
            # Inverte a chave para a próxima linha (reverse)
            current_key = current_key[::-1]
            player_data.append(decoded_line.strip())

        # Mapeamento dos índices + Mapeamento Dinâmico (para robustez)
        if len(player_data) > 50:
            self.pilot = WoFFPilot()
            self.pilot.source_file = fname
            self.pilot.last_updated = datetime.now().isoformat()
            
            def safe_get(idx):
                return player_data[idx] if len(player_data) > idx and player_data[idx] else ""
            
            self.pilot.fName = safe_get(4)
            self.pilot.sName = safe_get(5)
            self.pilot.name = f"{self.pilot.fName} {self.pilot.sName}".strip()
            self.pilot.rank = safe_get(3)
            
            # Mapeamento Dinâmico para garantir que os campos não falham
            for s in player_data:
                s_clean = s.strip()
                if not s_clean:
                    continue
                    
                # Nação
                if s_clean in ("France", "Britain", "Germany", "USA", "Belgium"):
                    self.pilot.nation = s_clean
                    
                # Status
                if s_clean in ("In Service", "Wounded", "KIA", "Leave", "Prisoner", "Dead", "Retired"):
                    self.pilot.status = s_clean
                    
                # Data de Nascimento
                if "/" in s_clean and len(s_clean) == 10 and s_clean[2] == "/" and s_clean[5] == "/":
                    self.pilot.birthDate = s_clean
                    
                # Biografia Narrativa
                if "joined" in s_clean.lower() or "enlisted" in s_clean.lower():
                    self.pilot.notes = s_clean

            # Índices fixos para estatísticas (confirmados no Java)
            self.pilot.squadron = safe_get(83)
            self.pilot.aircraft = safe_get(84)
            self.pilot.aerodrome = safe_get(88)
            self.pilot.sector = safe_get(89)
            self.pilot.missions = safe_get(46) if safe_get(46) else "0"
            self.pilot.claimsCount = safe_get(16) if safe_get(16) else "0"
            self.pilot.killsCount = safe_get(17) if safe_get(17) else "0"
            self.pilot.flminutes = safe_get(11) if safe_get(11) else "0"
            self.pilot.skill = safe_get(41) if safe_get(41) else "0"
            self.pilot.reputation = safe_get(52) if safe_get(52) else "0"
            self.pilot.birthPlace = safe_get(92)
            
            # Extrair ID da Foto (Índice 100 - confirmado no código Java do Pilot Log Editor)
            photo_id = safe_get(100)
            if photo_id and photo_id.isdigit():
                self.pilot.photo = photo_id
            
            # Datas (Campanha e Alistamento)
            d, m, y = safe_get(6), safe_get(7), safe_get(8)
            if d and m and y: 
                self.pilot.startDate = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
            
            d, m, y = safe_get(12), safe_get(13), safe_get(14)
            if d and m and y: 
                self.pilot.enlisted = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
            
            # Guardar strings brutais para debug
            self.raw_strings = player_data
            
            # ─── Extrair Membros do Esquadrão (AI Wingmen) ───
            self.wingmen = []
            wingmen_ranks = ["Lieutenant", "Capitaine", "Caporal", "Sergent", "Sous", "Major", "Colonel", "Private", "Corporal", "Oberleutnant", "Leutnant"]
            
            for s in player_data:
                s_clean = s.strip()
                # Uma string de wingman começa com uma patente e tem vários ';'
                if ";" in s_clean and len(s_clean) > 20 and any(s_clean.startswith(rank) for rank in wingmen_ranks):
                    parts = [p.strip() for p in s_clean.split(";")]
                    if len(parts) >= 6:
                        w = WoFFWingman()
                        w.rank = parts[0]
                        w.fName = parts[1]
                        w.sName = parts[2]
                        w.skill = parts[3] if len(parts) > 3 else "0"
                        w.morale = parts[4] if len(parts) > 4 else "0"
                        w.status = parts[5] if len(parts) > 5 else "Active"
                        
                        # Procurar biografia (costuma estar após muitos números, mas antes da data de nascimento)
                        for part in parts:
                            if "pilot" in part.lower() or "observer" in part.lower() or "outlook" in part.lower():
                                w.bio = part
                                break
                        
                        # Extrair Minutos de Voo se existirem no índice esperado (12)
                        if len(parts) > 12 and parts[12].isdigit():
                            w.flminutes = parts[12]
                            
                        self.wingmen.append(w)

            # ─── Extrair Medalhas Recebidas (Índices 19 a 26) ───
            self.decorations = []
            for i in range(19, 27):
                medal_str = safe_get(i)
                if medal_str and medal_str.lower() != "null":
                    # O formato pode ser "NomeDaMedalha;Data" ou apenas "NomeDaMedalha"
                    parts = medal_str.split(";")
                    medal_name = parts[0].strip()
                    if medal_name:
                        d = WoFFDecoration()
                        d.name = medal_name
                        d.date = parts[1].strip() if len(parts) > 1 and parts[1].strip() else ""
                        d.source_file = fname
                        self.decorations.append(d)
            
            log.info(f"  ✓ Dossier Decifrado! Piloto: {self.pilot.name} ({self.pilot.squadron}) | Wingmen: {len(self.wingmen)} | Medalhas: {len(self.decorations)}")
            return True
            
        log.warning("  Dossier decifrado, mas sem dados suficientes.")
        return False