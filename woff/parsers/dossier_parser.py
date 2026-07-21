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
                            pass
                        
                        key_index += 1
                        if key_index == len(current_key):
                            key_index = 0
                        hex_buffer = ""
                elif code != 32:
                    hex_buffer += char
                    
            current_key = current_key[::-1]
            player_data.append(decoded_line.strip())

        if len(player_data) > 50:
            self.pilot = WoFFPilot()
            self.pilot.source_file = fname
            self.pilot.last_updated = datetime.now().isoformat()
            
            def safe_get(idx):
                return player_data[idx] if len(player_data) > idx and player_data[idx] else ""
            
            # 1. Índices fixos para estatísticas (confirmados no Java)
            self.pilot.fName = safe_get(4)
            self.pilot.sName = safe_get(5)
            self.pilot.name = f"{self.pilot.fName} {self.pilot.sName}".strip()
            self.pilot.rank = safe_get(3)
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
            
            # Extração do ID da Foto centralizada (Índice 100)
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
            
            # 2. Heurísticas Dinâmicas com 'break' (para não capturar valores errados)
            for s in player_data:
                s_clean = s.strip()
                if not s_clean:
                    continue
                
                if not self.pilot.nation and s_clean in ("France", "Britain", "Germany", "USA", "Belgium"):
                    self.pilot.nation = s_clean
                    continue
                if not self.pilot.status and s_clean in ("In Service", "Wounded", "KIA", "Leave", "Prisoner", "Dead", "Retired"):
                    self.pilot.status = s_clean
                    continue
                if not self.pilot.birthDate and "/" in s_clean and len(s_clean) == 10 and s_clean[2] == "/" and s_clean[5] == "/":
                    self.pilot.birthDate = s_clean
                    continue
                if not self.pilot.notes and ("joined" in s_clean.lower() or "enlisted" in s_clean.lower()):
                    self.pilot.notes = s_clean
                    continue
            
            self.raw_strings = player_data
            
            # 3. Extrair Membros do Esquadrão (AI Wingmen)
            self.wingmen = []
            
            # FIX: Lista de patentes expandida para cobrir Britânicos, Franceses e Alemães
            wingmen_ranks = [
                # British (RFC/RNAS/RAF)
                "Lieutenant", "2nd Lieutenant", "Captain", "Major", "Colonel", 
                "Flight Lieutenant", "Flight Sergeant", "Sergeant", "Corporal", 
                "Private", "Air Mechanic",
                # French
                "Capitaine", "Sous-Lieutenant", "Adjudant", "Sergent", "Caporal", 
                "Maréchal-des-logis", "Brigadier",
                # German
                "Hauptmann", "Oberleutnant", "Leutnant", "Rittmeister", 
                "Vizefeldwebel", "Feldwebel", "Unteroffizier", "Gefreiter"
            ]
            
            for s in player_data:
                s_clean = s.strip()
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
                        
                        for part in parts:
                            if "pilot" in part.lower() or "observer" in part.lower() or "outlook" in part.lower():
                                w.bio = part
                                break
                        
                        if len(parts) > 12 and parts[12].isdigit():
                            w.flminutes = parts[12]
                            
                        self.wingmen.append(w)

            # 4. Extrair Medalhas Recebidas (Índices 19 a 26)
            self.decorations = []
            for i in range(19, 27):
                medal_str = safe_get(i)
                if medal_str and medal_str.lower() != "null":
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