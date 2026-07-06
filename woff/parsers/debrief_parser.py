#!/usr/bin/env python3
"""
Parser de Texto/Log (parsers/debrief_parser.py)
══════════════════════════════════════════════════════════════════
Responsável por fazer o parse dos ficheiros de debriefing em texto 
(.txt, .log) gerados pelo WoFF BHaH II.

Usa heurísticas de regex (definidas no maps.py) para extrair dados 
estruturados de missões e vitórias a partir de texto não estruturado.
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
import os
import re
from typing import List

# Importar modelos de dados, normalização e mapas de regex
from models import WoFFMission, WoFFVictory
from normalization import (
    normalize_date,
    normalize_mission_type,
    normalize_victory_type
)
from maps import DEBRIEF_REGEX

log = logging.getLogger("WoFFWatch")


class WoFFDebriefParser:
    """Extrai dados de missões e vitórias a partir de ficheiros de texto."""

    def __init__(self, pilot_id: str = ""):
        self.pilot_id  = pilot_id
        self.missions:  List[WoFFMission] = []
        self.victories: List[WoFFVictory] = []

    def parse(self, path: str) -> bool:
        """Inicia o parsing do ficheiro de texto."""
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
        """Extrai os detalhes da missão usando regex."""
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

        # Heurísticas para o resultado da missão
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
        """Extrai vitórias/claims usando regex."""
        for match in DEBRIEF_REGEX["KILL"].finditer(text):
            v = WoFFVictory()
            v.pilotId     = self.pilot_id
            v.source_file = fname
            v.enemyType   = match.group(1).strip()[:60]

            # Procura a hora mais próxima do match da vitória
            surround = text[max(0, match.start()-100):match.end()+100]
            tm = DEBRIEF_REGEX["TIME"].search(surround)
            if tm:
                v.time = tm.group(1)

            full = match.group(0).lower()
            v.victoryType = normalize_victory_type(full)

            # Ignora falsos positivos muito curtos (ex: "OOC")
            if len(v.enemyType) > 2:
                self.victories.append(v)