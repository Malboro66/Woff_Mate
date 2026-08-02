#!/usr/bin/env python3
"""
Parser de Dados do Piloto (parsers/pilot_data_parser.py)
══════════════════════════════════════════════════════════════════
"""
import os, re, logging
from typing import List, Optional
from ..models import WoFFPilot, WoFFMission, WoFFVictory
from ..normalization import normalize_mission_type, normalize_victory_type, normalize_date

log = logging.getLogger("WoFFWatch")

class WoFFPilotDataParser:
    def __init__(self):
        self.pilot: Optional[WoFFPilot] = None
        self.missions: List[WoFFMission] = []
        self.victories: List[WoFFVictory] = []

    @staticmethod
    def _bool_field(raw: str) -> bool:
        """Converte flags textuais/numéricas do PilotLog para booleano.

        Mantém paridade semântica com o parser XML: valores vazios e negações
        comuns são False; indicadores positivos como 1/yes/damaged/wounded são True.
        """
        value = str(raw or "").strip().lower()
        false_values = ("", "0", "false", "no", "none", "nein", "non", "undamaged")
        true_values = (
            "1", "true", "yes", "y", "damaged", "damage",
            "wounded", "wound", "injured",
        )
        if value in false_values:
            return False
        if value in true_values:
            return True
        if value.startswith(("no ", "not ")):
            return False
        return bool(value)

    def parse(self, path: str) -> bool:
        fname = os.path.basename(path).lower()
        if "dossier" in fname: return False

        pilot_match = re.match(r"(pilot\d+)", fname, re.I)
        if not pilot_match: return False
        
        pilot_name = pilot_match.group(1).replace("pilot", "Pilot ")
        
        if "squads" in fname: return self._parse_squads(path, pilot_name)
        elif "log" in fname: return self._parse_log(path, pilot_name)
        elif "claims" in fname: return self._parse_claims(path, pilot_name)
        return False

    def _parse_squads(self, path: str, pilot_name: str) -> bool:
        log.info(f"[TXT] Analisando Esquadrões: {os.path.basename(path)}")
        try:
            with open(path, "r", encoding="cp1252", errors="replace") as f: lines = f.readlines()
            if not lines: return False
            p = WoFFPilot()
            p.name = pilot_name
            p.source_file = os.path.basename(path)
            parts = [part.strip() for part in lines[-1].strip().split(";")]
            if len(parts) >= 12:
                p.squadron = parts[7]; p.aircraft = parts[8]; p.aerodrome = parts[6]; p.sector = parts[5]
                rank_match = re.search(r"rank:\s*([^\.]+)", parts[10], re.I)
                if rank_match: p.rank = rank_match.group(1).strip()
                p.startDate = normalize_date(f"{parts[0].replace('/','')}/{parts[1].replace('/','')}/{parts[2]}")
            self.pilot = p
            return True
        except Exception as e:
            log.error(f"  Falha ao ler {path}: {e}"); return False

    def _parse_log(self, path: str, pilot_name: str) -> bool:
        log.info(f"[TXT] Analisando Log de Missões: {os.path.basename(path)}")
        try:
            with open(path, "r", encoding="cp1252", errors="replace") as f: lines = f.readlines()
            for line in lines[1:]:
                line = line.strip()
                if not line or line.isdigit(): continue
                parts = [part.strip() for part in line.split(";")]
                if len(parts) >= 14:
                    m = WoFFMission()
                    m.source_file = os.path.basename(path)
                    m.pilotId = pilot_name
                    m.date = normalize_date(f"{parts[0].replace('/', '')}/{parts[1].replace('/', '')}/{parts[2]}")
                    if len(parts) > 4:
                        m.time = f"{parts[3].replace('h','').zfill(2)}:{parts[4].zfill(2)}"
                    m.sector = parts[5]
                    m.aircraft = parts[8] if len(parts) > 8 else ""
                    m.missionType = normalize_mission_type(parts[7]) if len(parts) > 7 else ""
                    m.duration = parts[10] if len(parts) > 10 else ""
                    m.squadron = parts[13]
                    # PilotLog.txt usa os campos 18 e 19 para dano na aeronave e
                    # ferimentos do piloto. Normalizamos defensivamente para manter
                    # paridade com os booleanos extraídos pelo parser XML.
                    m.damageReceived = (
                        self._bool_field(parts[18]) if len(parts) > 18 else False
                    )
                    m.woundsReceived = (
                        self._bool_field(parts[19]) if len(parts) > 19 else False
                    )
                    m.notes = (
                        parts[20][:500]
                        if len(parts) > 20
                        else parts[19][:500] if len(parts) > 19 else ""
                    )
                    m.result = "Shot Down — KIA" if "killed" in m.notes.lower() else "Crash Landing — Survived" if "crash" in m.notes.lower() else "Completed"
                    self.missions.append(m)
            
            # FIX: Criar placeholder pilot se não existir para que o handler e DB o possam usar
            if not self.pilot:
                self.pilot = WoFFPilot(name=pilot_name, source_file=os.path.basename(path))
                
            return bool(self.missions)
        except Exception as e:
            log.error(f"  Falha ao ler {path}: {e}"); return False

    def _parse_claims(self, path: str, pilot_name: str) -> bool:
        log.info(f"[TXT] Analisando Vitórias (Claims): {os.path.basename(path)}")
        try:
            with open(path, "r", encoding="cp1252", errors="replace") as f: lines = f.readlines()
            for line in lines[1:]:
                line = line.strip()
                if not line: continue
                parts = [part.strip() for part in line.split(";")]
                if len(parts) >= 12:
                    v = WoFFVictory()
                    v.source_file = os.path.basename(path)
                    v.pilotId = pilot_name
                    v.date = normalize_date(f"{parts[0]}/{parts[1]}/{parts[2]}")
                    v.time = f"{parts[3].replace('h','').zfill(2)}:{parts[4].zfill(2)}"
                    v.sector = parts[5]
                    v.aircraft = parts[8]
                    v.enemyType = parts[10]
                    v.victoryType = normalize_victory_type(parts[11])
                    v.confirmed = "confirmed" in parts[11].lower()
                    if len(parts) > 20: v.witnesses = f"{parts[18]} - {parts[19]} {parts[20]}".strip()
                    self.victories.append(v)
                    
            # FIX: Criar placeholder pilot se não existir
            if not self.pilot:
                self.pilot = WoFFPilot(name=pilot_name, source_file=os.path.basename(path))
                
            return bool(self.victories)
        except Exception as e:
            log.error(f"  Falha ao ler {path}: {e}"); return False