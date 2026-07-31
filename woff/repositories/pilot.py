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

from .base import BaseRepository

log = logging.getLogger("WoFFWatch")


class PilotRepository(BaseRepository):
    """Repositório especializado na entidade WoFFPilot."""

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