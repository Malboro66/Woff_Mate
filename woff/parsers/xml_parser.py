#!/usr/bin/env python3
"""
Parser de XML (parsers/xml_parser.py)
══════════════════════════════════════════════════════════════════
Responsável por fazer o parse dos ficheiros XML de campanha do 
WoFF BHaH II.

O WoFF guarda a carreira do piloto em XML. O esquema exacto pode 
variar entre versões — este parser usa busca flexível de elementos 
(usando um índice O(1) na raiz) e estratégias de fallback.
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional, List, Dict

# Importar modelos de dados e funções de normalização (assumindo que estão na raiz do projeto)
from models import WoFFPilot, WoFFMission, WoFFVictory, WoFFDecoration
from normalization import (
    normalize_nation,
    normalize_mission_type,
    normalize_status,
    normalize_victory_type,
    normalize_date
)

log = logging.getLogger("WoFFWatch")


class WoFFXMLParser:
    """Extrai dados de pilotos, missões, vitórias e condecorações de ficheiros XML."""

    def __init__(self):
        self.pilot:       Optional[WoFFPilot]  = None
        self.missions:    List[WoFFMission]    = []
        self.victories:   List[WoFFVictory]    = []
        self.decorations: List[WoFFDecoration] = []
        self._root:       Optional[ET.Element] = None
        self._root_idx:   Dict[str, List[str]] = {}

    def _build_index(self, root: ET.Element) -> dict:
        """Cria um índice case-insensitive para acesso O(1) das tags principais na raiz."""
        idx: Dict[str, List[str]] = {}
        for elem in root.iter():
            tag = elem.tag.split(":")[-1].lower()
            if elem.text and elem.text.strip():
                idx.setdefault(tag, []).append(elem.text.strip())
        return idx

    def _find_in_root(self, *tags: str) -> Optional[str]:
        """Procura no índice da raiz."""
        for tag in tags:
            vals = self._root_idx.get(tag.lower())
            if vals:
                return vals[0]
        return None

    def _find(self, node: ET.Element, *tags: str) -> Optional[str]:
        """Procura texto de elemento. Usa índice global se for a raiz, senão itera localmente."""
        if node is self._root:
            return self._find_in_root(*tags)
            
        tags_lower = {t.lower() for t in tags}
        for elem in node.iter():
            tag_l = elem.tag.split(":")[-1].lower()
            if tag_l in tags_lower and elem.text and elem.text.strip():
                return elem.text.strip()
        return None

    def _find_attr(self, node: ET.Element, attr: str, *tags: str) -> Optional[str]:
        """Procura um atributo específico dentro de tags."""
        for tag in tags:
            for elem in node.iter(tag):
                v = elem.get(attr) or elem.get(attr.lower()) or elem.get(attr.upper())
                if v:
                    return v.strip()
        return None

    def _bool_field(self, raw: str) -> bool:
        """Converte texto boleano do jogo em True/False."""
        return (raw or "").lower().strip() not in ("0", "false", "no", "none", "", "nein", "non")

    def parse(self, path: str) -> bool:
        """Inicia o parsing do ficheiro XML."""
        log.info(f"[XML] Analisando: {os.path.basename(path)}")
        try:
            tree = ET.parse(path)
            root = tree.getroot()
        except ET.ParseError as e:
            log.error(f"  Erro de XML em {path}: {e}")
            return False
        except Exception as e:
            log.error(f"  Falha ao ler {path}: {e}")
            return False

        self._root = root
        self._root_idx = self._build_index(root)
        
        self.pilot       = None
        self.missions    = []
        self.victories   = []
        self.decorations = []

        self._parse_pilot(root, path)
        self._parse_missions(root)
        self._parse_victories(root)
        self._parse_decorations(root)

        if self.pilot:
            log.info(
                f"  ✓ Piloto: {self.pilot.name} | "
                f"Missões: {len(self.missions)} | "
                f"Vitórias: {len(self.victories)} | "
                f"Condecorações: {len(self.decorations)}"
            )
            return True

        log.debug(f"  Sem dados de piloto em: {os.path.basename(path)}")
        return False

    def _parse_pilot(self, root: ET.Element, path: str):
        p = WoFFPilot()
        p.source_file  = os.path.basename(path)
        p.last_updated = datetime.now().isoformat()

        # Corrigido: Removido o fallback do nome do ficheiro para evitar pilotos falsos
        found_name = (
            self._find(root, "PilotName","Name","FullName","pilot_name","NomPilote","Pilotname") or
            self._find_attr(root, "name", "Pilot","pilot")
        )
        
        # Se não encontrámos uma tag explícita de nome de piloto, abortamos o parse deste XML
        if not found_name:
            return
            
        p.name = found_name
        
        # Corrigido: Removido "Title" da lista de rank (Title é o título da missão)
        p.rank      = self._find(root, "Rank","CurrentRank","Grade","rank") or ""
        
        p.nation    = normalize_nation(
            self._find(root, "Nation","Country","Side","Service","Pays","nation") or ""
        )
        p.squadron  = self._find(root, "Squadron","Unit","SquadronNumber","Sqd","Escadrille") or ""
        p.aircraft  = self._find(root, "Aircraft","Plane","CurrentAircraft","AircraftType","Avion") or ""
        p.aerodrome = self._find(root, "Aerodrome","Base","Field","HomeBase","Terrain","airfield") or ""
        p.sector    = self._find(root, "Sector","Front","Area","Region","Secteur") or ""
        p.startDate = normalize_date(
            self._find(root, "StartDate","JoinDate","CreatedDate","DateDebut","start_date") or ""
        )
        raw_status  = self._find(root, "Status","PilotStatus","Etat","state","alive") or ""
        p.status    = normalize_status(raw_status, root)
        p.notes     = self._find(root, "Notes","Biography","History","Background","Historique") or ""

        self.pilot = p

    def _parse_missions(self, root: ET.Element):
        """Procura e extrai todas as missões voadas."""
        if not self.pilot:
            return
        containers = (
            list(root.findall(".//Missions")) +
            list(root.findall(".//MissionLog")) +
            list(root.findall(".//missions")) +
            list(root.findall(".//FlightLog")) +
            list(root.findall(".//Sorties"))
        )
        for c in containers:
            for elem in c:
                if elem.tag.lower() in ("mission","sortie","flight","op","einsatz"):
                    m = self._parse_mission_elem(elem)
                    if m:
                        m.pilotId = self.pilot.id
                        self.missions.append(m)
                        
        # Fallback: Mission diretamente sob root
        if not self.missions:
            for elem in root.findall(".//Mission"):
                m = self._parse_mission_elem(elem)
                if m:
                    m.pilotId = self.pilot.id
                    self.missions.append(m)

    def _parse_mission_elem(self, elem: ET.Element) -> Optional[WoFFMission]:
        """Extrai os dados de uma missão individual."""
        m = WoFFMission()
        raw_date = (
            elem.get("date") or elem.get("Date") or
            self._find(elem, "Date","MissionDate","Datum","date") or ""
        )
        m.date = normalize_date(raw_date)
        if not m.date:
            return None

        m.missionType   = normalize_mission_type(
            elem.get("type") or elem.get("Type") or
            self._find(elem, "Type","MissionType","OrderType","Auftrag") or ""
        )
        m.aircraft      = self._find(elem, "Aircraft","Plane","AircraftType","Flugzeug") or ""
        m.duration      = self._find(elem, "Duration","Time","FlightTime","Hours","Dauer") or ""
        m.altitude      = self._find(elem, "Altitude","Height","MaxAltitude","Hoehe") or ""
        m.sector        = self._find(elem, "Sector","Area","Zone","Location","Abschnitt") or ""
        m.weather       = self._find(elem, "Weather","Conditions","Wetter") or ""
        m.enemyContacts = self._find(elem, "EnemyContacts","Contacts","Encounters","Feindkontakte") or "0"
        m.claimsCount   = self._find(elem, "Claims","Victories","kills","KillClaims","Abschuesse") or "0"
        m.notes         = self._find(elem, "Notes","Comment","Remarks","Bemerkung") or ""

        raw_result      = self._find(elem, "Result","Outcome","MissionResult","Ergebnis") or ""
        m.result        = self._parse_result(raw_result)

        dmg_raw = self._find(elem, "Damage","AircraftDamage","Schaeden") or ""
        m.damageReceived = self._bool_field(dmg_raw) if dmg_raw else False
        wnd_raw = self._find(elem, "Wounds","PilotWounds","Injured","Verwundung") or ""
        m.woundsReceived = self._bool_field(wnd_raw) if wnd_raw else False

        return m

    def _parse_result(self, raw: str) -> str:
        """Normaliza o resultado da missão através de heurísticas de texto."""
        rl = raw.lower()
        if not rl:                                               return "Uneventful"
        if any(k in rl for k in ("kia","killed","dead")):       return "Shot Down — KIA"
        if "wound" in rl and ("shot" in rl or "down" in rl):   return "Shot Down — Wounded"
        if "shot down" in rl or "abgeschossen" in rl:           return "Shot Down — Survived"
        if "force" in rl and "enemy" in rl:                     return "Force-Landed (Enemy Lines)"
        if "force" in rl and "land" in rl:                      return "Force-Landed (Friendly Lines)"
        if "crash" in rl:                                        return "Crash Landing — Survived"
        if "emergency" in rl:                                    return "Emergency Landing"
        if "damage" in rl:                                       return "Aircraft Damaged (Returned)"
        if "major" in rl:                                        return "Major Engagement"
        if "minor" in rl:                                        return "Minor Engagement"
        if "uneventful" in rl:                                   return "Uneventful"
        return raw.strip()

    def _parse_victories(self, root: ET.Element):
        """Procura e extrai todas as vitórias/claims."""
        if not self.pilot:
            return
        for tag in ("Victory","Kill","Claim","VictoryClaim","AerialVictory","Abschuss"):
            for elem in root.findall(f".//{tag}"):
                v = self._parse_victory_elem(elem)
                if v:
                    v.pilotId = self.pilot.id
                    self.victories.append(v)

    def _parse_victory_elem(self, elem: ET.Element) -> Optional[WoFFVictory]:
        """Extrai os dados de uma vitória individual."""
        v = WoFFVictory()
        v.date = normalize_date(
            elem.get("date") or self._find(elem, "Date","date","Datum") or ""
        )
        v.time        = self._find(elem, "Time","time","Uhrzeit") or ""
        v.enemyType   = self._find(elem, "EnemyType","Aircraft","Type","enemy","Feindtyp") or ""
        raw_type      = self._find(elem, "Type","VictoryType","Result","outcome","Ergebnis") or ""
        v.victoryType = normalize_victory_type(raw_type)
        v.location    = self._find(elem, "Location","Where","Area","Place","Ort") or ""
        raw_conf      = self._find(elem, "Confirmed","Status","Validation","Bestaetigt") or "0"
        v.confirmed   = raw_conf.lower() in ("true","1","yes","confirmed","ok","ja","oui")
        v.witnesses   = self._find(elem, "Witnesses","ConfirmedBy","Observer","Zeugen") or ""
        v.notes       = self._find(elem, "Notes","Comment","Remarks") or ""
        if not v.date and not v.enemyType:
            return None
        return v

    def _parse_decorations(self, root: ET.Element):
        """Procura e extrai condecorações e medalhas."""
        if not self.pilot:
            return
        for tag in ("Decoration","Award","Medal","Honour","Honor","Auszeichnung","Orden"):
            for elem in root.findall(f".//{tag}"):
                d = WoFFDecoration()
                d.pilotId  = self.pilot.id
                d.name     = (self._find(elem, "Name","Award","Medal","Title") or elem.text or "").strip()
                d.date     = normalize_date(self._find(elem, "Date","date","Datum","Awarded") or "")
                d.citation = self._find(elem, "Citation","Reason","Notes","Begruendung") or ""
                if d.name:
                    self.decorations.append(d)