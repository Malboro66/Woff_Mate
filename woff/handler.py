#!/usr/bin/env python3
"""
Módulo de Eventos e Parsers (handler.py)
══════════════════════════════════════════════════════════════════
Contém a lógica de monitorização de ficheiros (watchdog), as guardas 
de estabilidade e os parsers (XML e TXT) para extrair os dados do 
WoFF BHaH II.

Componentes:
- FileStabilityGuard: Aguarda que o jogo termine de escrever nos ficheiros.
- WoFFXMLParser: Extrai dados de ficheiros XML de campanha.
- WoFFDebriefParser: Extrai dados de ficheiros de texto/log de debriefing.
- WoFFEventHandler: Recebe os eventos do sistema e dispara o processamento.
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional, List, Dict

from watchdog.events import FileSystemEventHandler

# Importar modelos e normalização dos módulos locais
from models import WoFFPilot, WoFFMission, WoFFVictory, WoFFDecoration
from normalization import (
    normalize_nation, normalize_mission_type, normalize_status,
    normalize_victory_type, normalize_date
)
from maps import DEBRIEF_REGEX
from parsers.xml_parser import WoFFXMLParser
from parsers.debrief_parser import WoFFDebriefParser

log = logging.getLogger("WoFFWatch")


# ──────────────────────────────────────────────────────────────
# GUARDIA DE ESTABILIDADE DO FICHEIRO
# ──────────────────────────────────────────────────────────────

class FileStabilityGuard:
    """
    Aguarda que o WoFF termine de escrever um ficheiro antes de fazer parse.
    O WoFF pode disparar eventos de file system enquanto ainda está a escrever,
    o que resulta em XML truncado ou texto incompleto.
    """
    def __init__(self, timeout: float = 3.0, interval: float = 0.15):
        self.timeout  = timeout
        self.interval = interval

    def wait(self, path: str) -> bool:
        if not os.path.exists(path):
            return False
        prev_size = -1
        elapsed   = 0.0
        while elapsed < self.timeout:
            try:
                size = os.path.getsize(path)
            except OSError:
                time.sleep(self.interval)
                elapsed += self.interval
                continue
            if size == prev_size and size > 0:
                log.debug(f"Ficheiro estável em {elapsed:.1f}s: {os.path.basename(path)}")
                return True
            prev_size = size
            time.sleep(self.interval)
            elapsed  += self.interval
        log.warning(f"Timeout de estabilidade ({self.timeout}s): {os.path.basename(path)}")
        return False


# ──────────────────────────────────────────────────────────────
# PARSER XML
# ──────────────────────────────────────────────────────────────

class WoFFXMLParser:
    def __init__(self):
        self.pilot:       Optional[WoFFPilot]  = None
        self.missions:    List[WoFFMission]    = []
        self.victories:   List[WoFFVictory]    = []
        self.decorations: List[WoFFDecoration] = []
        self._root:       Optional[ET.Element] = None
        self._root_idx:   Dict[str, List[str]] = {}

    def _build_index(self, root: ET.Element) -> dict:
        """Cria um índice case-insensitive para acesso O(1) das tags principais."""
        idx: Dict[str, List[str]] = {}
        for elem in root.iter():
            tag = elem.tag.split(":")[-1].lower()
            if elem.text and elem.text.strip():
                idx.setdefault(tag, []).append(elem.text.strip())
        return idx

    def _find_in_root(self, *tags: str) -> Optional[str]:
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
        for tag in tags:
            for elem in node.iter(tag):
                v = elem.get(attr) or elem.get(attr.lower()) or elem.get(attr.upper())
                if v:
                    return v.strip()
        return None

    def _bool_field(self, raw: str) -> bool:
        return (raw or "").lower().strip() not in ("0", "false", "no", "none", "", "nein", "non")

    def parse(self, path: str) -> bool:
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

        p.name = (
            self._find(root, "PilotName","Name","FullName","pilot_name","NomPilote","Pilotname") or
            self._find_attr(root, "name", "Pilot","pilot") or
            os.path.splitext(os.path.basename(path))[0]
        )
        p.nation    = normalize_nation(
            self._find(root, "Nation","Country","Side","Service","Pays","nation") or ""
        )
        p.rank      = self._find(root, "Rank","CurrentRank","Grade","rank","Title") or ""
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

        if p.name:
            self.pilot = p

    def _parse_missions(self, root: ET.Element):
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
        if not self.missions:
            for elem in root.findall(".//Mission"):
                m = self._parse_mission_elem(elem)
                if m:
                    m.pilotId = self.pilot.id
                    self.missions.append(m)

    def _parse_mission_elem(self, elem: ET.Element) -> Optional[WoFFMission]:
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
        if not self.pilot:
            return
        for tag in ("Victory","Kill","Claim","VictoryClaim","AerialVictory","Abschuss"):
            for elem in root.findall(f".//{tag}"):
                v = self._parse_victory_elem(elem)
                if v:
                    v.pilotId = self.pilot.id
                    self.victories.append(v)

    def _parse_victory_elem(self, elem: ET.Element) -> Optional[WoFFVictory]:
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


# ──────────────────────────────────────────────────────────────
# PARSER TXT/LOG
# ──────────────────────────────────────────────────────────────

class WoFFDebriefParser:
    def __init__(self, pilot_id: str = ""):
        self.pilot_id  = pilot_id
        self.missions:  List[WoFFMission] = []
        self.victories: List[WoFFVictory] = []

    def parse(self, path: str) -> bool:
        log.info(f"[TXT] Analisando: {os.path.basename(path)}")
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception as e:
            log.error(f"  Falha ao ler {path}: {e}")
            return False

        self.missions  = []
        self.victories = []
        fname = os.path.basename(path)

        self._extract_mission(text, fname)
        self._extract_victories(text, fname)

        found = bool(self.missions or self.victories)
        if found:
            log.info(f"  ✓ Debrief: {len(self.missions)} missão(ões), {len(self.victories)} reivindicação(ões)")
        else:
            log.debug(f"  Sem dados estruturados em: {fname}")
        return found

    def _extract_mission(self, text: str, fname: str):
        m = WoFFMission()
        m.pilotId     = self.pilot_id
        m.source_file = fname

        dm = DEBRIEF_REGEX["DATE"].search(text)
        if dm:
            m.date = normalize_date(dm.group(1))

        tm = DEBRIEF_REGEX["TYPE"].search(text)
        if tm:
            m.missionType = normalize_mission_type(tm.group(1))

        dur = DEBRIEF_REGEX["DURATION"].search(text)
        if dur:
            m.duration = dur.group(1).replace(",", ".")

        ac = DEBRIEF_REGEX["AIRCRAFT"].search(text)
        if ac:
            m.aircraft = ac.group(1).strip()[:50]

        sec = DEBRIEF_REGEX["SECTOR"].search(text)
        if sec:
            m.sector = sec.group(1).strip()[:60]

        cnt = DEBRIEF_REGEX["CONTACTS"].search(text)
        if cnt:
            m.enemyContacts = cnt.group(1)

        cl = DEBRIEF_REGEX["CLAIMS"].search(text)
        if cl:
            m.claimsCount = cl.group(1)

        tl = text.lower()
        m.damageReceived = bool(re.search(
            r"aircraft\s*damaged|plane\s*hit|engine\s*hit|wing\s*damage|fuselage\s*damage",
            tl))
        m.woundsReceived = bool(re.search(
            r"pilot\s*wounded|wound|injured|grazed|flesh\s*wound|verwundet",
            tl))

        if re.search(r"killed|kia|abgeschossen.*tot", tl):
            m.result = "Shot Down — KIA"
        elif re.search(r"shot\s+down.*wound|wound.*shot\s+down", tl):
            m.result = "Shot Down — Wounded"
        elif re.search(r"force.{0,10}land.{0,20}enemy|feindl.*gelandet", tl):
            m.result = "Force-Landed (Enemy Lines)"
        elif re.search(r"force.{0,10}land", tl):
            m.result = "Force-Landed (Friendly Lines)"
        elif re.search(r"crash.{0,20}land|bruchlandung", tl):
            m.result = "Crash Landing — Survived"
        elif m.damageReceived:
            m.result = "Aircraft Damaged (Returned)"
        else:
            m.result = "Uneventful"

        if m.date or m.missionType:
            self.missions.append(m)

    def _extract_victories(self, text: str, fname: str):
        for match in DEBRIEF_REGEX["KILL"].finditer(text):
            v = WoFFVictory()
            v.pilotId     = self.pilot_id
            v.source_file = fname
            v.enemyType   = match.group(1).strip()[:60]

            surround = text[max(0, match.start()-100):match.end()+100]
            tm = DEBRIEF_REGEX["TIME"].search(surround)
            if tm:
                v.time = tm.group(1)

            full = match.group(0).lower()
            v.victoryType = normalize_victory_type(full)

            if len(v.enemyType) > 2:
                self.victories.append(v)


# ──────────────────────────────────────────────────────────────
# HANDLER DE EVENTOS COM THREADPOOL
# ──────────────────────────────────────────────────────────────

class WoFFEventHandler(FileSystemEventHandler):
    WATCHED_EXT = {".xml", ".txt", ".log"}
    IGNORED     = {"desktop.ini", "thumbs.db", ".tmp", "~", ".bak", ".lnk"}

    def __init__(self, config, exporter, discovery=None, pilot_id=None):
        self.config    = config
        self.exporter  = exporter
        self.discovery = discovery
        self.pilot_id  = pilot_id
        
        self.guard = FileStabilityGuard(
            timeout  = config.stability_timeout_sec,
            interval = config.stability_check_interval_sec,
        )
        
        self._pool = ThreadPoolExecutor(max_workers=config.max_workers, thread_name_prefix="woff-worker")
        self._inflight: set[str] = set()
        self._inflight_lock = threading.Lock()

    def on_modified(self, event):
        if not event.is_directory:
            self._handle(event.src_path, "modified")

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path, "created")

    def _handle(self, path: str, event_type: str):
        bn  = os.path.basename(path).lower()
        ext = os.path.splitext(path)[1].lower()
        if ext not in self.WATCHED_EXT:
            return
        if any(p in bn for p in self.IGNORED):
            return
            
        with self._inflight_lock:
            if path in self._inflight:
                return
            self._inflight.add(path)
            
        self._pool.submit(self._process, path, event_type)

    def _process(self, path: str, event_type: str):
        try:
            log.info(f"Detectado [{event_type}]: {os.path.basename(path)}")

            if self.discovery:
                time.sleep(0.4)
                if os.path.exists(path):
                    self.discovery.log_file(path, event_type)

            if not self.guard.wait(path):
                log.warning(f"Ignorado (ficheiro instável): {os.path.basename(path)}")
                return

            ext = os.path.splitext(path)[1].lower()
            if ext == ".xml":
                self._do_xml(path)
            elif ext in (".txt", ".log"):
                self._do_text(path)
        except Exception as e:
            log.exception(f"Erro inesperado a processar {path}: {e}")
        finally:
            time.sleep(1.0) # Evita reprocessar imediato de modificações encadeadas
            with self._inflight_lock:
                self._inflight.discard(path)

    def _do_xml(self, path: str):
        parser = WoFFXMLParser()
        if parser.parse(path):
            self.exporter.merge_and_write(
                parser.pilot, parser.missions,
                parser.victories, parser.decorations
            )

    def _do_text(self, path: str):
        parser = WoFFDebriefParser(pilot_id=self.pilot_id or "")
        if parser.parse(path):
            self.exporter.merge_and_write(None, parser.missions, parser.victories, [])
            
    def shutdown(self):
        log.info("A aguardar conclusão das threads de processamento...")
        self._pool.shutdown(wait=True)