#!/usr/bin/env python3
"""
Parser de Dados do Piloto (parsers/pilot_data_parser.py)
══════════════════════════════════════════════════════════════════
Faz o parse dos ficheiros de texto delimitados por ; gerados pelo 
WoFF BHaH II na pasta CampaignData/Pilots/.

Baseado na engenharia reversa do código Java do Pilot Log Editor (JJJ65):
- Usa encoding Windows-1252 (cp1252) para suportar acentos.
- Ignora a primeira linha que contém o contador de registos.
- Mapeia os índices exatos do split(";").
══════════════════════════════════════════════════════════════════
"""

import os
import re
import json
import logging
from typing import List, Optional
from models import WoFFPilot, WoFFMission, WoFFVictory
from normalization import normalize_mission_type, normalize_victory_type, normalize_date

log = logging.getLogger("WoFFWatch")

# Caminho para o ficheiro de mapeamento
MAPPING_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "pilot_mapping.json")

def get_pilot_name(pilot_id: str) -> str:
    """Lê o pilot_mapping.json e retorna o nome real do piloto."""
    try:
        with open(MAPPING_PATH, "r", encoding="utf-8") as f:
            mapping = json.load(f)
        return mapping.get(pilot_id, pilot_id)
    except Exception:
        return pilot_id

class WoFFPilotDataParser:
    def __init__(self):
        self.pilot: Optional[WoFFPilot] = None
        self.missions: List[WoFFMission] = []
        self.victories: List[WoFFVictory] = []

    def parse(self, path: str) -> bool:
        fname = os.path.basename(path).lower()
        
        if "dossier" in fname:
            return False

        pilot_match = re.match(r"(pilot\d+)", fname, re.I)
        if not pilot_match:
            return False
            
        pilot_id_raw = pilot_match.group(1)
        pilot_id_formatted = pilot_id_raw.replace("pilot", "Pilot ")
        pilot_name = get_pilot_name(pilot_id_formatted)
        
        if "squads" in fname:
            return self._parse_squads(path, pilot_name)
        elif "log" in fname:
            return self._parse_log(path, pilot_name)
        elif "claims" in fname:
            return self._parse_claims(path, pilot_name)
            
        return False

    def _parse_squads(self, path: str, pilot_name: str) -> bool:
        log.info(f"[TXT] Analisando Esquadrões: {os.path.basename(path)}")
        try:
            # Encoding Windows-1252 para suportar acentos
            with open(path, "r", encoding="cp1252", errors="replace") as f:
                lines = f.readlines()
                
            if not lines:
                return False
                
            p = WoFFPilot()
            p.name = pilot_name
            p.source_file = os.path.basename(path)
            
            last_line = lines[-1].strip()
            parts = [part.strip() for part in last_line.split(";")]
            
            if len(parts) >= 12:
                p.squadron = parts[7]
                p.aircraft = parts[8]
                p.aerodrome = parts[6]
                p.sector = parts[5]
                
                text = parts[10]
                rank_match = re.search(r"rank:\s*([^\.]+)", text, re.I)
                if rank_match:
                    p.rank = rank_match.group(1).strip()
                    
                p.startDate = normalize_date(f"{parts[0].replace('/','')}/{parts[1].replace('/','')}/{parts[2]}")
                
            self.pilot = p
            log.info(f"  ✓ Piloto atualizado: {p.name} ({p.squadron})")
            return True
            
        except Exception as e:
            log.error(f"  Falha ao ler {path}: {e}")
            return False

    def _parse_log(self, path: str, pilot_name: str) -> bool:
        log.info(f"[TXT] Analisando Log de Missões: {os.path.basename(path)}")
        try:
            with open(path, "r", encoding="cp1252", errors="replace") as f:
                lines = f.readlines()
                
            if len(lines) <= 1:
                return False
                
            # A primeira linha é o contador de registos, ignoramos (linhas[1:])
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                    
                parts = [part.strip() for part in line.split(";")]
                
                # Confirmado pelo código Java: precisa de pelo menos 14 partes
                if len(parts) >= 14:
                    m = WoFFMission()
                    m.source_file = os.path.basename(path)
                    m.pilotId = pilot_name
                    
                    # parts[0]=Dia, parts[1]=Mes, parts[2]=Ano
                    day = parts[0].replace('/', '').replace('\\', '')
                    month = parts[1].replace('/', '').replace('\\', '')
                    year = parts[2]
                    m.date = normalize_date(f"{day}/{month}/{year}")
                    
                    # Java: missions[x][5] = Region, [6] = Airbase, [7] = MissionType, [8] = Aircraft, [10] = Duration, [13] = Squad
                    m.sector = parts[5]
                    m.aerodrome = parts[6]
                    m.missionType = normalize_mission_type(parts[7])
                    m.aircraft = parts[8]
                    m.duration = parts[10] if len(parts) > 10 else ""
                    m.squadron = parts[13]
                    
                    # Java: missions[x][19] = Log Text (Narrativa)
                    narrative = parts[19] if len(parts) > 19 else ""
                    m.notes = narrative[:500]
                    
                    # Heuristica de resultado
                    if "killed" in narrative.lower() or "kia" in narrative.lower():
                        m.result = "Shot Down — KIA"
                    elif "crash" in narrative.lower():
                        m.result = "Crash Landing — Survived"
                    else:
                        m.result = "Completed"
                        
                    self.missions.append(m)
                    
            log.info(f"  ✓ {len(self.missions)} missões extraídas do log.")
            return bool(self.missions)
            
        except Exception as e:
            log.error(f"  Falha ao ler {path}: {e}")
            return False

    def _parse_claims(self, path: str, pilot_name: str) -> bool:
        log.info(f"[TXT] Analisando Vitórias (Claims): {os.path.basename(path)}")
        try:
            with open(path, "r", encoding="cp1252", errors="replace") as f:
                lines = f.readlines()
                
            if len(lines) <= 1:
                return False
                
            # A primeira linha é o cabeçalho, ignoramos
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                    
                parts = [part.strip() for part in line.split(";")]
                
                # Java: kills[x][0-2]=Data, [3]=Hora, [4]=Min, [5]=Region, [7]=MissionType, [8]=Aircraft, [10]=EnemyCraft, [11]=Circumstances
                if len(parts) >= 12:
                    v = WoFFVictory()
                    v.source_file = os.path.basename(path)
                    v.pilotId = pilot_name
                    
                    day = parts[0]
                    month = parts[1]
                    year = parts[2]
                    v.date = normalize_date(f"{day}/{month}/{year}")
                    
                    v.time = f"{parts[3].replace('h','').zfill(2)}:{parts[4].zfill(2)}"
                    v.sector = parts[5]
                    v.missionType = normalize_mission_type(parts[7])
                    v.aircraft = parts[8]
                    v.enemyType = parts[10]
                    v.victoryType = normalize_victory_type(parts[11])
                    
                    # Java: verifica se kills[x][11] contém "Confirmed"
                    v.confirmed = "confirmed" in parts[11].lower()
                    
                    # ──────────────────────────────────────────────────────────────
                    # NOVO: Extrair Testemunhas (Colunas 18, 19 e 20)
                    # ──────────────────────────────────────────────────────────────
                    if len(parts) > 20:
                        witness_squad = parts[18]
                        witness_name = f"{parts[19]} {parts[20]}".strip()
                        if witness_name:
                            v.witnesses = f"{witness_squad} - {witness_name}"
                    elif len(parts) > 18:
                        v.witnesses = parts[18]
                    
                    self.victories.append(v)
                    
            log.info(f"  ✓ {len(self.victories)} vitórias extraídas.")
            return bool(self.victories)
            
        except Exception as e:
            log.error(f"  Falha ao ler {path}: {e}")
            return False