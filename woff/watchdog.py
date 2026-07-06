#!/usr/bin/env python3
"""
WoFF BHaH II Watchdog v1.1
══════════════════════════════════════════════════════════════════
Monitoriza os ficheiros de campanha do Wings over Flanders Fields:
Between Heaven and Hell II e exporta dados de missões e pilotos
em JSON compatível com a aplicação WoFFBase.

Melhorias v1.1:
- Escrita atómica e thread-safe do JSON (sem corrupção de dados)
- Correção de condições de corrida (race conditions) no processamento
- Índice de tags XML para performance O(1) na leitura
- Normalização de status via regex (word boundaries) para evitar falsos positivos
- Uso de ThreadPoolExecutor e filas para processamento eficiente
- Configuração validada via Dataclasses
- Encerramento gracioso (graceful shutdown) das threads

Modos de uso:
  Normal:     python woff_watchdog.py
  Descoberta: python woff_watchdog.py --discover
  Teste:      python woff_watchdog.py --test
  Ajuda:      python woff_watchdog.py --help
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import re
import shutil
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# ──────────────────────────────────────────────────────────────
# VERIFICAÇÃO DE DEPENDÊNCIAS
# ──────────────────────────────────────────────────────────────

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print(
        "\n[ERRO] Biblioteca 'watchdog' não encontrada.\n"
        "Instala com:  pip install watchdog\n"
        "Ou:           pip install -r requirements.txt\n"
    )
    sys.exit(1)

# ──────────────────────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────────────────────

LOG_FORMAT = "[%(asctime)s] %(levelname)-8s  %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt="%H:%M:%S")
log = logging.getLogger("WoFFWatch")

# ──────────────────────────────────────────────────────────────
# CONFIGURAÇÃO
# ──────────────────────────────────────────────────────────────

@dataclass
class WatchdogConfig:
    watch_paths: List[str] = field(default_factory=lambda: [
        "A:\\OBDSoftware\\WOFF\\campaigns",
        "A:\\OBDSoftware\\WOFF\\WoFF\\campaigns",
        "A:\\OBDSoftware\\WOFF\\log",
        "A:\\OBDSoftware\\WOFF\\WoFF\\log"
    ])
    export_path: str = "C:\\Users\\Public\\WoFFBase\\woff_export.json"
    watched_extensions: List[str] = field(default_factory=lambda: [".xml", ".txt", ".log"])
    stability_timeout_sec: float = 3.0
    stability_check_interval_sec: float = 0.15
    backup_export: bool = True
    discovery_log_path: str = "woff_discovery.log"
    log_level: str = "INFO"
    max_workers: int = 4
    export_schema_version: str = "1.1"

    @classmethod
    def from_dict(cls, d: dict) -> "WatchdogConfig":
        valid = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**valid)

    def to_dict(self) -> dict:
        return asdict(self)


def load_config(path: str) -> WatchdogConfig:
    p = Path(path)
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = WatchdogConfig.from_dict(data)
            log.info(f"Configuração carregada: {path}")
            return cfg
        except Exception as e:
            log.warning(f"Erro ao ler config ({e}) — usando valores padrão.")
    else:
        try:
            default_cfg = WatchdogConfig()
            with open(p, "w", encoding="utf-8") as f:
                json.dump(default_cfg.to_dict(), f, indent=2, ensure_ascii=False)
            log.info(f"Ficheiro config.json criado — edita os caminhos conforme necessário.")
            return default_cfg
        except Exception as e:
            log.warning(f"Não foi possível escrever config.json: {e}")
    
    return WatchdogConfig()

# ──────────────────────────────────────────────────────────────
# MODELOS DE DADOS  (compatíveis com WoFFBase React app)
# ──────────────────────────────────────────────────────────────

def _uid() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class WoFFPilot:
    id:           str = field(default_factory=_uid)
    name:         str = ""
    nation:       str = ""
    rank:         str = ""
    squadron:     str = ""
    aircraft:     str = ""
    aerodrome:    str = ""
    sector:       str = ""
    startDate:    str = ""
    status:       str = "Active"
    notes:        str = ""
    source_file:  str = ""
    last_updated: str = ""


@dataclass
class WoFFMission:
    id:             str  = field(default_factory=_uid)
    pilotId:        str  = ""
    date:           str  = ""
    missionType:    str  = ""
    aircraft:       str  = ""
    duration:       str  = ""
    altitude:       str  = ""
    sector:         str  = ""
    weather:        str  = ""
    enemyContacts:  str  = "0"
    claimsCount:    str  = "0"
    result:         str  = ""
    damageReceived: bool = False
    woundsReceived: bool = False
    notes:          str  = ""
    source_file:    str  = ""


@dataclass
class WoFFVictory:
    id:          str  = field(default_factory=_uid)
    pilotId:     str  = ""
    date:        str  = ""
    time:        str  = ""
    missionId:   str  = ""
    enemyType:   str  = ""
    victoryType: str  = ""
    location:    str  = ""
    confirmed:   bool = False
    witnesses:   str  = ""
    notes:       str  = ""
    source_file: str  = ""


@dataclass
class WoFFDecoration:
    id:          str = field(default_factory=_uid)
    pilotId:     str = ""
    name:        str = ""
    date:        str = ""
    citation:    str = ""
    source_file: str = ""


@dataclass
class WoFFExport:
    """Estrutura raiz exportada — compatível com o WoFFBase app."""
    pilots:      List[dict] = field(default_factory=list)
    missions:    List[dict] = field(default_factory=list)
    victories:   List[dict] = field(default_factory=list)
    decorations: List[dict] = field(default_factory=list)
    diary:       List[dict] = field(default_factory=list)
    meta:        dict       = field(default_factory=dict)

# ──────────────────────────────────────────────────────────────
# TABELAS DE NORMALIZAÇÃO
# ──────────────────────────────────────────────────────────────

NATION_MAP = {
    "rfc": "RFC", "royal flying corps": "RFC", "british": "RFC", "uk": "RFC",
    "rnas": "RNAS", "royal naval air service": "RNAS", "naval": "RNAS",
    "raf": "RAF", "royal air force": "RAF",
    "french": "French", "france": "French", "aeronautique": "French", "fr": "French",
    "german": "German", "germany": "German", "luftstreitkrafte": "German",
    "deutsche": "German", "de": "German",
    "american": "American", "usas": "American", "usa": "American", "us": "American",
    "belgian": "Belgian", "belgium": "Belgian", "belge": "Belgian",
}

MISSION_TYPE_MAP = {
    "offensive patrol": "Offensive Patrol (OP)", " op ": "Offensive Patrol (OP)",
    "defensive patrol": "Defensive Patrol",
    "close air support": "Close Air Support (CAS)", "cas": "Close Air Support (CAS)",
    "artillery": "Artillery Observation (Art.Obs.)", "art. obs": "Artillery Observation (Art.Obs.)",
    "photographic": "Photographic Reconnaissance", "photo recon": "Photographic Reconnaissance",
    "strategic recon": "Strategic Reconnaissance", "long.range recon": "Strategic Reconnaissance",
    "bombing": "Bombing Raid (Tactical)", "bomb": "Bombing Raid (Tactical)",
    "balloon": "Balloon Busting",
    "escort": "Escort Duty",
    "ground attack": "Ground Attack / Strafing", "straf": "Ground Attack / Strafing",
}

# Tabela de Status substituída por regex para evitar falsos positivos (ex: "deadline" apanhava "dead")
STATUS_PATTERNS = [
    (re.compile(r"\b(kia|killed|mort|tot|deceased)\b", re.I), "KIA"),
    (re.compile(r"\b(pow|prisoner|captured|prisonnier)\b", re.I), "PoW"),
    (re.compile(r"\bmia\b|\bmissing\b", re.I), "MIA"),
    (re.compile(r"\b(invalided|retired|discharged)\b", re.I), "Invalided Out"),
    (re.compile(r"\b(survived|end\s+of\s+war)\b", re.I), "Survived War"),
]
WOUND_RE = re.compile(r"\b(wound|hospital|injured|bless)\b", re.I)
SEVERE_RE = re.compile(r"\b(serious|severe|critical|heavy|grave)\b", re.I)

VICTORY_TYPE_MAP = {
    ("flame", "fire", "burned", "flamme"):           "Destroyed — In Flames",
    ("structural", "break", "broke apart", "broke"): "Destroyed — Structural Failure",
    ("ooc", "out of control", "spin"):               "Out of Control (OOC)",
    ("forced to land", "force land", "landed"):      "Forced to Land",
    ("driven down", "driven"):                       "Driven Down (Unconfirmed)",
    ("balloon", "drachen", "caquot"):                "Balloon Destroyed (Flames)",
}


def _map(raw: str, mapping: dict, fallback: str = "") -> str:
    if not raw:
        return fallback
    raw_l = raw.strip().lower()
    for keys, value in mapping.items():
        if isinstance(keys, tuple):
            if any(k in raw_l for k in keys):
                return value
        elif keys in raw_l:
            return value
    return raw.strip() or fallback


def normalize_nation(raw: str) -> str:
    return _map(raw, NATION_MAP, "RFC")


def normalize_mission_type(raw: str) -> str:
    return _map(raw, MISSION_TYPE_MAP, raw.strip() if raw else "")


def normalize_status(raw: str, root: Optional[ET.Element] = None) -> str:
    if not raw:
        return "Active"
    
    for pattern, status in STATUS_PATTERNS:
        if pattern.search(raw):
            return status
            
    if WOUND_RE.search(raw):
        severity = ""
        if root is not None:
            sev_elem = root.find(".//WoundSeverity") or root.find(".//Severity")
            if sev_elem is not None and sev_elem.text:
                severity = sev_elem.text.lower()
        if SEVERE_RE.search(severity):
            return "Seriously Wounded"
        return "Lightly Wounded"
        
    return "Active"


def normalize_victory_type(raw: str) -> str:
    return _map(raw, VICTORY_TYPE_MAP, "Out of Control (OOC)")


def normalize_date(raw: str) -> str:
    """Converte vários formatos de data para YYYY-MM-DD."""
    if not raw:
        return ""
    raw = raw.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    
    m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$", raw)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
        
    m = re.match(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})$", raw)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
        
    months = {
        "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
        "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
        "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,"jul":7,"aug":8,
        "sep":9,"oct":10,"nov":11,"dec":12,
        "janvier":1,"février":2,"mars":3,"avril":4,"mai":5,"juin":6,
        "juillet":7,"août":8,"septembre":9,"octobre":10,"novembre":11,"décembre":12,
    }
    raw_l = raw.lower()
    for name, num in months.items():
        if name in raw_l:
            nums = [int(n) for n in re.findall(r"\d+", raw)]
            year  = next((n for n in nums if n > 100), None)
            day   = next((n for n in nums if 1 <= n <= 31), None)
            if year and day:
                return f"{year}-{str(num).zfill(2)}-{str(day).zfill(2)}"
                
    log.debug(f"Data não reconhecida: '{raw}'")
    return raw

# ──────────────────────────────────────────────────────────────
# GUARDIA DE ESTABILIDADE DO FICHEIRO
# ──────────────────────────────────────────────────────────────

class FileStabilityGuard:
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
    DATE_RE = re.compile(
        r"(?:date|mission\s*date|sortie\s*date)[:\s]+"
        r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4}"
        r"|\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2}"
        r"|\d{1,2}\s+\w+\s+\d{4})",
        re.IGNORECASE
    )
    TYPE_RE    = re.compile(r"(?:mission\s*type|order|sortie\s*type|type)[:\s]+([\w\s\(\)/\-]+?)(?:\n|,|\.)", re.IGNORECASE)
    DUR_RE     = re.compile(r"(?:duration|flight\s*time|hours)[:\s]+(\d+(?:[.,]\d+)?)\s*(?:h(?:ours?|r)?)?", re.IGNORECASE)
    AC_RE      = re.compile(r"(?:aircraft|plane|flying|flew)[:\s]+([\w\s\.\-]+?)(?:\n|,|\.)", re.IGNORECASE)
    SECTOR_RE  = re.compile(r"(?:sector|area|region|front)[:\s]+([\w\s\-]+?)(?:\n|,|\.)", re.IGNORECASE)
    CONTACT_RE = re.compile(r"(?:enemy\s*contact|hostile|encountered?)[:\s]+(\d+)", re.IGNORECASE)
    CLAIM_RE   = re.compile(r"(?:claim|kill|victory|abschuss)[:\s]+(\d+)", re.IGNORECASE)
    
    # Regex corrigido (quantificador {3,50} válido)
    KILL_RE    = re.compile(
        r"(?:destroyed|shot\s+down|forced\s+to\s+land|out\s+of\s+control|OOC|driven\s+down)"
        r"\s*([\w\s\.\-]{3,50})"
        r"(?:\s+(?:in\s+flames?|ooc|structural|forced))?",
        re.IGNORECASE
    )
    TIME_RE    = re.compile(r"(\d{1,2}:\d{2})")

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

        dm = self.DATE_RE.search(text)
        if dm:
            m.date = normalize_date(dm.group(1))

        tm = self.TYPE_RE.search(text)
        if tm:
            m.missionType = normalize_mission_type(tm.group(1))

        dur = self.DUR_RE.search(text)
        if dur:
            m.duration = dur.group(1).replace(",", ".")

        ac = self.AC_RE.search(text)
        if ac:
            m.aircraft = ac.group(1).strip()[:50]

        sec = self.SECTOR_RE.search(text)
        if sec:
            m.sector = sec.group(1).strip()[:60]

        cnt = self.CONTACT_RE.search(text)
        if cnt:
            m.enemyContacts = cnt.group(1)

        cl = self.CLAIM_RE.search(text)
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
        for match in self.KILL_RE.finditer(text):
            v = WoFFVictory()
            v.pilotId     = self.pilot_id
            v.source_file = fname
            v.enemyType   = match.group(1).strip()[:60]

            surround = text[max(0, match.start()-100):match.end()+100]
            tm = self.TIME_RE.search(surround)
            if tm:
                v.time = tm.group(1)

            full = match.group(0).lower()
            v.victoryType = normalize_victory_type(full)

            if len(v.enemyType) > 2:
                self.victories.append(v)

# ──────────────────────────────────────────────────────────────
# EXPORTADOR JSON THREAD-SAFE
# ──────────────────────────────────────────────────────────────

class JSONExporter:
    def __init__(self, export_path: str, backup: bool = True, schema_version: str = "1.1"):
        self.export_path = Path(export_path)
        self.backup = backup
        self.schema_version = schema_version
        self._lock = threading.RLock() # Lock reentrante
        self.export_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> WoFFExport:
        if not self.export_path.exists():
            return WoFFExport(meta={"created": datetime.now().isoformat()})
        try:
            with open(self.export_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            return WoFFExport(
                pilots      = d.get("pilots", []),
                missions    = d.get("missions", []),
                victories   = d.get("victories", []),
                decorations = d.get("decorations", []),
                diary       = d.get("diary", []),
                meta        = d.get("meta", {})
            )
        except Exception as e:
            log.error(f"Falha ao carregar export existente: {e}")
            return WoFFExport()

    def _atomic_write(self, data: dict) -> None:
        """Escrita atómica para evitar corrupção de ficheiros JSON."""
        tmp_path = self.export_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        if self.backup and self.export_path.exists():
            bak_path = self.export_path.with_suffix(".json.bak")
            try:
                shutil.copy2(self.export_path, bak_path)
            except Exception as e:
                log.warning(f"Falha ao criar backup: {e}")
                
        os.replace(tmp_path, self.export_path) # Atómico no mesmo filesystem

    def merge_and_write(self,
                        pilot:       Optional[WoFFPilot],
                        missions:    List[WoFFMission],
                        victories:   List[WoFFVictory],
                        decorations: List[WoFFDecoration]) -> bool:
        with self._lock:
            exp = self.load()

            pilot_id = ""
            if pilot:
                existing = next(
                    (p for p in exp.pilots
                     if p.get("name","").lower() == pilot.name.lower()),
                    None
                )
                if existing:
                    pilot_id = existing["id"]
                    pd = asdict(pilot)
                    pd["id"] = pilot_id
                    exp.pilots = [pd if p["id"] == pilot_id else p for p in exp.pilots]
                    log.info(f"  Piloto actualizado: {pilot.name}")
                else:
                    pilot_id = pilot.id
                    exp.pilots.append(asdict(pilot))
                    log.info(f"  Novo piloto adicionado: {pilot.name}")
            else:
                # Se for TXT sem piloto definido, não adivinhamos o primeiro da lista
                # Apenas processamos se vier um pilot_id externamente definido
                pilot_id = next((m.pilotId for m in missions if m.pilotId), "")
                if not pilot_id:
                    log.warning("  Ficheiro de debrief sem piloto associado. Missões não associadas.")
                    return False

            # Missões — chave de deduplicação robusta
            m_keys = {(m.get("pilotId",""), m.get("date",""), m.get("missionType",""), m.get("aircraft",""))
                      for m in exp.missions}
            added_m = 0
            for m in missions:
                m.pilotId = pilot_id
                k = (m.pilotId, m.date, m.missionType, m.aircraft)
                if k not in m_keys:
                    exp.missions.append(asdict(m))
                    m_keys.add(k)
                    added_m += 1

            # Vitórias — chave: piloto + data + hora + tipo de inimigo
            v_keys = {(v.get("pilotId",""), v.get("date",""), v.get("time",""), v.get("enemyType",""))
                      for v in exp.victories}
            added_v = 0
            for v in victories:
                v.pilotId = pilot_id
                k = (v.pilotId, v.date, v.time, v.enemyType)
                if k not in v_keys:
                    exp.victories.append(asdict(v))
                    v_keys.add(k)
                    added_v += 1

            # Condecorações — chave: piloto + nome
            d_keys = {(d.get("pilotId",""), d.get("name","")) for d in exp.decorations}
            added_d = 0
            for d in decorations:
                d.pilotId = pilot_id
                k = (d.pilotId, d.name)
                if k not in d_keys:
                    exp.decorations.append(asdict(d))
                    d_keys.add(k)
                    added_d += 1

            if added_m or added_v or added_d:
                log.info(f"  + {added_m} missões, {added_v} vitórias, {added_d} condecorações")

            exp.meta["last_updated"] = datetime.now().isoformat()
            exp.meta["source"]       = "WoFF BHaH II Watchdog v1.1"
            exp.meta["schema_version"] = self.schema_version

            try:
                self._atomic_write(asdict(exp))
                size_kb = self.export_path.stat().st_size / 1024
                log.info(f"  ✓ Export escrito: {self.export_path} ({size_kb:.1f} KB)")
                return True
            except Exception as e:
                log.error(f"Falha ao escrever export: {e}")
                return False

# ──────────────────────────────────────────────────────────────
# MODO DESCOBERTA
# ──────────────────────────────────────────────────────────────

class DiscoveryLogger:
    PREVIEW_LIMIT = 12_000

    def __init__(self, log_path: str):
        self.log_path = Path(log_path)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'═'*60}\n")
            f.write(f"SESSÃO DE DESCOBERTA — {datetime.now().isoformat()}\n")
            f.write(f"{'═'*60}\n")
        log.info(f"Modo descoberta activo — log: {self.log_path}")

    def log_file(self, path: str, event_type: str):
        try:
            p = Path(path)
            size = p.stat().st_size if p.exists() else 0
            ext  = p.suffix.lower()
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now().isoformat()}] Evento: {event_type.upper()}\n")
                f.write(f"Ficheiro: {path}\n")
                f.write(f"Tamanho: {size} bytes | Extensão: {ext}\n")
                if size > 0 and size < 1_000_000 and ext in (".xml",".txt",".log",".ini",".cfg",".csv"):
                    try:
                        with open(p, "r", encoding="utf-8", errors="replace") as src:
                            content = src.read(self.PREVIEW_LIMIT)
                        f.write(f"{'─'*40} Conteúdo ({min(size, self.PREVIEW_LIMIT)}/{size}B) {'─'*10}\n")
                        f.write(content)
                        f.write(f"\n{'─'*60}\n")
                    except Exception as e:
                        f.write(f"Erro ao ler conteúdo: {e}\n")
                elif size >= 1_000_000:
                    f.write(f"[Ficheiro muito grande — sem preview]\n")
                else:
                    f.write(f"[Binário ou extensão desconhecida — sem preview]\n")
            log.info(f"[DISCOVER] {event_type}: {p.name} ({size}B)")
        except Exception as e:
            log.error(f"Erro no discovery log: {e}")

# ──────────────────────────────────────────────────────────────
# HANDLER DE EVENTOS COM THREADPOOL
# ──────────────────────────────────────────────────────────────

class WoFFEventHandler(FileSystemEventHandler):
    WATCHED_EXT = {".xml", ".txt", ".log"}
    IGNORED     = {"desktop.ini", "thumbs.db", ".tmp", "~", ".bak", ".lnk"}

    def __init__(self, config: WatchdogConfig, exporter: JSONExporter,
                 discovery: Optional[DiscoveryLogger] = None,
                 pilot_id: Optional[str] = None):
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

# ──────────────────────────────────────────────────────────────
# ORQUESTRADOR PRINCIPAL
# ──────────────────────────────────────────────────────────────

class WoFFWatchdog:

    def __init__(self, config: WatchdogConfig, discovery: bool = False, pilot_id: str = ""):
        self.config    = config
        self.exporter  = JSONExporter(config.export_path, config.backup_export, config.export_schema_version)
        self.discovery = DiscoveryLogger(config.discovery_log_path) if discovery else None
        self.pilot_id  = pilot_id
        self.observers: List[Observer] = []
        self._handler: Optional[WoFFEventHandler] = None
        self._stop_event = threading.Event()

    def start(self) -> bool:
        paths = self.config.watch_paths
        valid = [p for p in paths if os.path.exists(p)]
        missing = [p for p in paths if not os.path.exists(p)]

        for p in valid:
            log.info(f"  ✓ Monitorizar: {p}")
        for p in missing:
            log.warning(f"  ✗ Não encontrado: {p}")

        if not valid:
            log.error(
                "\nNenhum caminho válido encontrado!\n"
                "Edita config.json com os caminhos correctos da tua instalação WoFF.\n"
            )
            return False

        self._handler = WoFFEventHandler(
            self.config, self.exporter, self.discovery, self.pilot_id
        )
        for path in valid:
            obs = Observer()
            obs.schedule(self._handler, path, recursive=True)
            obs.start()
            self.observers.append(obs)

        log.info(f"\nWatchdog activo — {len(valid)} caminho(s) em monitorização")
        log.info(f"Export: {self.config.export_path}")
        if self.discovery:
            log.info(f"Discovery log: {self.config.discovery_log_path}")
        log.info("Pressiona Ctrl+C para parar.\n")
        return True

    def run_forever(self):
        try:
            while not self._stop_event.is_set():
                self._stop_event.wait(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        log.info("A parar watchdog...")
        self._stop_event.set()
        for obs in self.observers:
            obs.stop()
        for obs in self.observers:
            obs.join(timeout=5)
            
        if self._handler:
            self._handler.shutdown()
            
        log.info("Watchdog parado.")

# ──────────────────────────────────────────────────────────────
# MODO TESTE — XML simulado
# ──────────────────────────────────────────────────────────────

MOCK_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Campaign>
  <Pilot>
    <PilotName>James Percival Hartley</PilotName>
    <Nation>RFC</Nation>
    <Rank>Captain</Rank>
    <Squadron>No. 56 Squadron RFC</Squadron>
    <Aircraft>SE.5a</Aircraft>
    <Aerodrome>Filescamp Farm</Aerodrome>
    <Sector>Arras</Sector>
    <StartDate>1917-04-01</StartDate>
    <Status>Active</Status>
    <Notes>Transferred from No. 60 Sqn after Bloody April.</Notes>
  </Pilot>
  <Missions>
    <Mission>
      <Date>1917-04-06</Date>
      <Type>Offensive Patrol</Type>
      <Aircraft>SE.5a</Aircraft>
      <Duration>1.5</Duration>
      <Altitude>12000</Altitude>
      <Sector>Arras</Sector>
      <Weather>Clear</Weather>
      <EnemyContacts>4</EnemyContacts>
      <Claims>1</Claims>
      <Result>Major Engagement</Result>
      <Damage>0</Damage>
      <Wounds>0</Wounds>
      <Notes>Intercepted Jasta 11 formation east of Arras.</Notes>
    </Mission>
  </Missions>
  <Victories>
    <Victory>
      <Date>1917-04-06</Date>
      <Time>10:35</Time>
      <EnemyType>Albatros D.III</EnemyType>
      <Type>Out of Control</Type>
      <Confirmed>true</Confirmed>
      <Witnesses>Lt. Richardson, 56 Sqn</Witnesses>
    </Victory>
  </Victories>
  <Decorations>
    <Decoration>
      <Name>Military Cross (MC)</Name>
      <Date>1917-04-15</Date>
      <Citation>For conspicuous gallantry.</Citation>
    </Decoration>
  </Decorations>
</Campaign>
"""


def run_test(config: WatchdogConfig):
    import tempfile
    sep = "═" * 50
    log.info(f"\n{sep}")
    log.info("MODO TESTE — XML simulado do WoFF")
    log.info(sep)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".xml", delete=False, encoding="utf-8"
    ) as f:
        f.write(MOCK_XML)
        tmp = f.name

    try:
        parser = WoFFXMLParser()
        ok     = parser.parse(tmp)

        if ok and parser.pilot:
            p = parser.pilot
            log.info(f"\nPiloto:")
            log.info(f"  Nome:     {p.name}")
            log.info(f"  Nação:    {p.nation}")
            log.info(f"  Posto:    {p.rank}")
            log.info(f"  Estado:   {p.status}")
            log.info(f"\nMissões ({len(parser.missions)}):")
            for m in parser.missions:
                log.info(f"  [{m.date}] {m.missionType} — {m.result}")
            log.info(f"\nVitórias ({len(parser.victories)}):")
            for v in parser.victories:
                log.info(f"  [{v.date}] {v.enemyType} — {v.victoryType} | Confirmado: {v.confirmed}")

            test_path = os.path.join(
                os.path.dirname(os.path.abspath(config.export_path)),
                "woff_test_export.json"
            )
            exp = JSONExporter(test_path, backup=False)
            exp.merge_and_write(
                parser.pilot, parser.missions,
                parser.victories, parser.decorations
            )
            log.info(f"\n✓ Export de teste escrito em: {test_path}")
            log.info(f"\n{sep}")
            log.info("Teste concluído com sucesso!")
        else:
            log.error("✗ Parser não encontrou dados — verifica o XML")
    finally:
        os.unlink(tmp)

# ──────────────────────────────────────────────────────────────
# PONTO DE ENTRADA
# ──────────────────────────────────────────────────────────────

BANNER = r"""
╔══════════════════════════════════════════════════════════╗
║      ✈  WoFF BHaH II — Watchdog  v1.1  ✈              ║
║   Wings over Flanders Fields · Companion Sync Tool      ║
╚══════════════════════════════════════════════════════════╝
"""


def main():
    ap = argparse.ArgumentParser(
        description="WoFF BHaH II Watchdog — sincroniza campanha com WoFFBase",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Exemplos:
  python woff_watchdog.py                    Monitorização normal
  python woff_watchdog.py --discover         Regista todos os ficheiros detectados
  python woff_watchdog.py --test             Testa o parser com dados simulados
  python woff_watchdog.py --config meu.json  Usa ficheiro de config alternativo
  python woff_watchdog.py --verbose          Log detalhado (DEBUG)
"""
    )
    ap.add_argument("--config",   default="config.json",
                    help="Caminho para config.json (padrão: config.json)")
    ap.add_argument("--discover", action="store_true",
                    help="Modo descoberta: regista todos os ficheiros detectados")
    ap.add_argument("--test",     action="store_true",
                    help="Modo teste: corre parser com XML simulado")
    ap.add_argument("--pilot",    default="",
                    help="ID do piloto para associar a ficheiros de texto")
    ap.add_argument("--verbose",  action="store_true",
                    help="Log detalhado (DEBUG)")
    args = ap.parse_args()

    print(BANNER)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    cfg = load_config(args.config)
    if args.verbose or cfg.log_level == "DEBUG":
        logging.getLogger().setLevel(logging.DEBUG)

    if args.test:
        run_test(cfg)
        return

    dog = WoFFWatchdog(cfg, discovery=args.discover, pilot_id=args.pilot)
    if dog.start():
        dog.run_forever()


if __name__ == "__main__":
    main()