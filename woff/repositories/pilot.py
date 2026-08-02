#!/usr/bin/env python3
"""
Repositório de Pilotos (repositories/pilot.py)
══════════════════════════════════════════════════════════════════
Responsável por:
  - Queries de estado do piloto
  - Resolução de identidade (placeholder → UUID)
  - Datas do jogo
  - Histórico de missões (cross-query com pilots)
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import re
import os
import sqlite3
import logging
from typing import Optional, Tuple, Dict, Any, List

from ..models import WoFFPilot, WoFFMission, WoFFVictory

from .base import BaseRepository

log = logging.getLogger("WoFFWatch")


class PilotRepository(BaseRepository):
    """Repositório especializado na entidade WoFFPilot."""

    def upsert_pilot(
        self,
        pilot: Optional[WoFFPilot],
        missions: List[WoFFMission],
        victories: List[WoFFVictory],
    ) -> Optional[str]:
        """Insere/atualiza o piloto e resolve o pilot_id para ficheiros de missão."""
        cursor = self._conn.cursor()
        pilot_id = ""

        if pilot:
            cursor.execute("SELECT id FROM pilots WHERE name = ?", (pilot.name,))
            row = cursor.fetchone()

            if not row and re.match(r"^Pilot \d+$", pilot.name):
                pilot_num_match = re.match(r"^Pilot (\d+)$", pilot.name)
                if pilot_num_match:
                    pilot_num = pilot_num_match.group(1)
                    cursor.execute(
                        "SELECT id FROM pilots WHERE source_file GLOB ?",
                        (f"Pilot{pilot_num}[A-Za-z]*.txt",)
                    )
                    row = cursor.fetchone()

            if row:
                pilot_id = row[0]
                name_val = "" if re.match(r"^Pilot \d+$", pilot.name) else pilot.name

                cursor.execute("""
                    UPDATE pilots SET
                        name=COALESCE(NULLIF(?, ''), name),
                        fName=COALESCE(NULLIF(?, ''), fName),
                        sName=COALESCE(NULLIF(?, ''), sName),
                        nation=COALESCE(NULLIF(?, ''), nation),
                        rank=COALESCE(NULLIF(?, ''), rank),
                        squadron=COALESCE(NULLIF(?, ''), squadron),
                        aircraft=COALESCE(NULLIF(?, ''), aircraft),
                        aerodrome=COALESCE(NULLIF(?, ''), aerodrome),
                        sector=COALESCE(NULLIF(?, ''), sector),
                        startDate=COALESCE(NULLIF(?, ''), startDate),
                        enlisted=COALESCE(NULLIF(?, ''), enlisted),
                        status=COALESCE(NULLIF(?, ''), status),
                        notes=COALESCE(NULLIF(?, ''), notes),
                        photo=COALESCE(NULLIF(?, ''), photo),
                        birthDate=COALESCE(NULLIF(?, ''), birthDate),
                        birthPlace=COALESCE(NULLIF(?, ''), birthPlace),
                        missions=COALESCE(NULLIF(?, ''), missions),
                        flminutes=COALESCE(NULLIF(?, ''), flminutes),
                        claimsCount=COALESCE(NULLIF(?, ''), claimsCount),
                        killsCount=COALESCE(NULLIF(?, ''), killsCount),
                        skill=COALESCE(NULLIF(?, ''), skill),
                        reputation=COALESCE(NULLIF(?, ''), reputation),
                        source_file=COALESCE(NULLIF(?, ''), source_file),
                        last_updated=?
                    WHERE id=?
                """, (
                    name_val, pilot.fName, pilot.sName, pilot.nation,
                    pilot.rank, pilot.squadron, pilot.aircraft, pilot.aerodrome,
                    pilot.sector, pilot.startDate, pilot.enlisted, pilot.status,
                    pilot.notes, pilot.photo, pilot.birthDate, pilot.birthPlace,
                    pilot.missions, pilot.flminutes, pilot.claimsCount,
                    pilot.killsCount, pilot.skill, pilot.reputation,
                    pilot.source_file, pilot.last_updated, pilot_id
                ))
                log.info(f"  Piloto atualizado na DB: ID {pilot_id}")
            else:
                pilot_id = pilot.id
                cursor.execute("""
                    INSERT OR IGNORE INTO pilots (
                        id, name, fName, sName, nation, rank, squadron,
                        aircraft, aerodrome, sector, startDate, enlisted,
                        status, notes, photo, birthDate, birthPlace, missions,
                        flminutes, claimsCount, killsCount, skill, reputation,
                        source_file, last_updated
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    pilot.id, pilot.name, pilot.fName, pilot.sName,
                    pilot.nation, pilot.rank, pilot.squadron, pilot.aircraft,
                    pilot.aerodrome, pilot.sector, pilot.startDate,
                    pilot.enlisted, pilot.status, pilot.notes, pilot.photo,
                    pilot.birthDate, pilot.birthPlace, pilot.missions,
                    pilot.flminutes, pilot.claimsCount, pilot.killsCount,
                    pilot.skill, pilot.reputation, pilot.source_file,
                    pilot.last_updated
                ))
                log.info(f"  Novo piloto adicionado à DB: {pilot.name}")
        else:
            source_file = next((m.source_file for m in missions if m.source_file), None)
            if not source_file and victories:
                source_file = next(
                    (v.source_file for v in victories if v.source_file), None
                )

            if source_file:
                pilot_num_match = re.match(
                    r"^Pilot(\d+)", os.path.basename(source_file), re.I
                )
                if pilot_num_match:
                    pilot_num = pilot_num_match.group(1)
                    cursor.execute(
                        "SELECT id FROM pilots WHERE source_file GLOB ?",
                        (f"Pilot{pilot_num}[A-Za-z]*.txt",)
                    )
                    row = cursor.fetchone()
                    if row:
                        pilot_id = row[0]

        if not pilot_id:
            pilot_id = next((m.pilotId for m in missions if m.pilotId), "")
            if not pilot_id:
                log.warning("  Ficheiro de debrief sem piloto associado. Ignorado.")
                return None
        return pilot_id

    def get_pilot_state(self, pilot_name: str) -> Tuple[Optional[str], Optional[str]]:
        """Busca o status e rank atual do piloto."""
        with self._lock:
            try:
                row = self._fetch_one(
                    "SELECT status, rank FROM pilots WHERE name = ?",
                    (pilot_name,),
                )
                return (row[0], row[1]) if row else (None, None)
            except sqlite3.Error:
                log.exception(f"Erro ao buscar estado do piloto {pilot_name}")
                return None, None

    def resolve_pilot_id(
        self, name: str, source_file: Optional[str] = None
    ) -> Optional[str]:
        """
        Resolve um nome de piloto (real ou placeholder 'Pilot X') para o UUID.
        """
        with self._lock:
            try:
                # 1. Nome exato
                row = self._fetch_one(
                    "SELECT id FROM pilots WHERE name = ?",
                    (name,),
                )
                if row:
                    return row[0]

                # 2. Fallback GLOB para "Pilot X"
                if source_file and re.match(r"^Pilot \d+$", name):
                    match = re.match(
                        r"^Pilot(\d+)", os.path.basename(source_file), re.I
                    )
                    if match:
                        pilot_num = match.group(1)
                        row = self._fetch_one(
                            "SELECT id FROM pilots WHERE source_file GLOB ?",
                            (f"Pilot{pilot_num}[A-Za-z]*.txt",),
                        )
                        if row:
                            return row[0]
                return None
            except sqlite3.Error:
                log.exception(f"Erro ao resolver pilot_id para {name}")
                return None

    def get_pilot_id_by_name(self, pilot_name: str) -> Optional[str]:
        """Busca o ID do piloto pelo nome de forma segura."""
        return self.resolve_pilot_id(pilot_name)

    def get_pilot_game_date(self, pilot_id: str) -> str:
        """Busca a data mais recente do piloto (missão mais recente ou startDate)."""
        with self._lock:
            try:
                row = self._fetch_one(
                    "SELECT date FROM missions WHERE pilotId = ? ORDER BY date DESC LIMIT 1",
                    (pilot_id,),
                )
                if row and row[0]:
                    return row[0]

                row = self._fetch_one(
                    "SELECT startDate FROM pilots WHERE id = ?",
                    (pilot_id,),
                )
                if row and row[0]:
                    return row[0]
                return "1917-01-01"
            except sqlite3.Error:
                log.exception("Erro ao buscar data do jogo")
                return "1917-01-01"

    def get_mission_and_history(
        self, pilot_identifier: str, mission_id: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """Busca o piloto, a missão EXATA e o histórico de missões."""
        with self._lock:
            conn = self._conn
            conn.row_factory = sqlite3.Row
            try:
                pilot = conn.execute(
                    "SELECT * FROM pilots WHERE id = ? OR name = ?",
                    (pilot_identifier, pilot_identifier),
                ).fetchone()
                if not pilot:
                    return None, None, []

                current_mission = conn.execute(
                    "SELECT * FROM missions WHERE id = ? AND pilotId = ?",
                    (mission_id, pilot["id"]),
                ).fetchone()
                if not current_mission:
                    return dict(pilot), None, []

                history = conn.execute(
                    """SELECT * FROM missions WHERE pilotId = ?
                       ORDER BY date DESC, time DESC LIMIT 10""",
                    (pilot["id"],),
                ).fetchall()
                return dict(pilot), dict(current_mission), [dict(m) for m in history]
            except sqlite3.Error:
                log.exception("Erro ao buscar missão/histórico")
                return None, None, []
            finally:
                conn.row_factory = None
