#!/usr/bin/env python3
"""
Parser de Logs de Missão (parsers/mission_log_parser.py)
══════════════════════════════════════════════════════════════════
Extrai dados ricos do ficheiro de log gerado pelo WoFF durante o voo.
Lê o bloco XML <Mission> no início do ficheiro e o log textual no final.
══════════════════════════════════════════════════════════════════
"""

import os
import re
import logging
import xml.etree.ElementTree as ET
from typing import Optional, List
from models import WoFFMission, WoFFPilot
from normalization import normalize_date, normalize_coordinates

log = logging.getLogger("WoFFWatch")

class WoFFMissionLogParser:
    def __init__(self):
        self.mission: Optional[WoFFMission] = None
        self.pilot: Optional[WoFFPilot] = None
        self.squad_members: List[str] = []
        self.flight_plan: List[str] = []
        self.briefing: str = ""
        self.debriefing: str = ""

    def parse(self, path: str) -> bool:
        log.info(f"[LOG] Analisando Log de Missão: {os.path.basename(path)}")
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            log.error(f"  Falha ao ler {path}: {e}")
            return False

        # 1. Extrair o bloco XML <Mission>...</Mission>
        xml_match = re.search(r"<Mission>(.*?)</Mission>", content, re.DOTALL)
        if not xml_match:
            log.warning("  Bloco <Mission> não encontrado no log.")
            return False
            
        xml_str = "<Mission>" + xml_match.group(1) + "</Mission>"
        
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as e:
            log.error(f"  Erro de XML no log: {e}")
            return False

        # 2. Extrair Parâmetros e Briefing
        params = root.find("Params")
        if params is not None:
            date_str = params.get("Date", "") # Formato do jogo: M/D/YYYY (ex: 9/20/1915)
            self.mission = WoFFMission()
            parts = date_str.split("/")
            if len(parts) == 3:
                # Converte M/D/YYYY para YYYY-MM-DD
                self.mission.date = f"{parts[2]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
            
            self.mission.weather = params.get("Weather", "Unknown").replace("OFFDynamicMissionWeather.xml", "Dynamic")

        overview = root.find("Overview")
        if overview is not None and overview.text:
            self.briefing = overview.text.strip()

        # 3. Encontrar a formação do jogador e membros do esquadrão
        # 3. Encontrar a formação do jogador e membros do esquadrão
        for formation in root.findall("AirFormation"):
            is_player_formation = False
            for unit in formation.findall("Unit"):
                if unit.get("IsPlayer") == "y":
                    is_player_formation = True
                    break

            if is_player_formation:
                self.pilot = WoFFPilot()
                self.pilot.nation = formation.get("Country", "")
                self.pilot.squadron = formation.get("SquadName", "")
                
                if self.mission:
                    self.mission.sector = self.pilot.squadron
                    self.mission.aircraft = unit.get("Type", "")
                    
                # Extrai membros do esquadrão (AI)
                for u in formation.findall("Unit"):
                    ac_type = u.get("Type", "")
                    fname = u.get("PilotFirstName", "")
                    lname = u.get("PilotLastName", "")
                    role = "Player" if u.get("IsPlayer") == "y" else "Wingman"
                    if fname:
                        self.squad_members.append(f"{role}: {fname} {lname} ({ac_type})")
                    else:
                        self.squad_members.append(f"{role}: [Player] ({ac_type})")
                    
                # Extrai Plano de Voo (Waypoints) com Coordenadas Decimais
                route = formation.find("Route")
                if route is not None:
                    for wp in route.findall("Waypoint"):
                        wp_type = wp.get("Type", "")
                        alt = wp.get("Alt", "0")
                        lat_raw = wp.get("Lat", "")
                        lon_raw = wp.get("Lon", "")
                        
                        # Converte as coordenadas para decimal
                        lat_dec = normalize_coordinates(lat_raw)
                        lon_dec = normalize_coordinates(lon_raw)
                        
                        # Guarda como dicionário para a Fase 3 (Mapas)
                        self.flight_plan.append({
                            "type": wp_type,
                            "altitude": alt,
                            "lat": lat_dec,
                            "lon": lon_dec,
                            "raw_lat": lat_raw,
                            "raw_lon": lon_raw
                        })
                break

        # 4. Extrair Debriefing do texto pós-XML
        text_after_xml = content[xml_match.end():]
        
        if "forced landing on friendly field" in text_after_xml.lower():
            self.debriefing = "Forced landing on friendly field"
            if self.mission: self.mission.result = "Force-Landed (Friendly Lines)"
        elif "MissionEnded" in text_after_xml:
            self.debriefing = "Mission Ended Successfully"
            if self.mission: self.mission.result = "Completed"
            
        return True