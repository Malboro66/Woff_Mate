#!/usr/bin/env python3
"""
Repositório de Missões (repositories/mission.py)
══════════════════════════════════════════════════════════════════
Responsável por queries e operações específicas da entidade WoFFMission.
Nota: O INSERT em massa de missões permanece no DatabaseManager (Unit of Work)
porque é coordenado dentro de uma transação cross-entidade.
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import sqlite3
import logging
from typing import List, Dict, Any, Tuple

from ..models import WoFFMission, WoFFVictory, WoFFDecoration

from .base import BaseRepository

log = logging.getLogger("WoFFWatch")


class MissionRepository(BaseRepository):
    """Repositório especializado na entidade WoFFMission."""

    def upsert_mission(
        self,
        pilot_id: str,
        missions: List[WoFFMission],
        victories: List[WoFFVictory],
        decorations: List[WoFFDecoration],
    ) -> Tuple[int, int, int]:
        """Insere missões, vitórias e condecorações associadas ao piloto."""
        cursor = self._conn.cursor()
        added_m = 0
        for m in missions:
            m.pilotId = pilot_id
            cursor.execute("""
                INSERT OR IGNORE INTO missions (
                    id, pilotId, date, time, missionType, aircraft, duration,
                    altitude, sector, squadron, weather, enemyContacts,
                    claimsCount, result, damageReceived, woundsReceived, notes,
                    source_file
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                m.id, m.pilotId, m.date, m.time, m.missionType, m.aircraft,
                m.duration, m.altitude, m.sector, m.squadron, m.weather,
                m.enemyContacts, m.claimsCount, m.result,
                m.damageReceived, m.woundsReceived, m.notes,
                m.source_file
            ))
            added_m += cursor.rowcount

        added_v = 0
        for v in victories:
            v.pilotId = pilot_id
            cursor.execute("""
                INSERT OR IGNORE INTO victories (
                    id, pilotId, date, time, missionId, enemyType, victoryType,
                    location, confirmed, witnesses, notes, sector, aircraft,
                    source_file
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                v.id, v.pilotId, v.date, v.time, v.missionId, v.enemyType,
                v.victoryType, v.location, v.confirmed, v.witnesses,
                v.notes, v.sector, v.aircraft, v.source_file
            ))
            added_v += cursor.rowcount

        added_d = 0
        for d in decorations:
            d.pilotId = pilot_id
            cursor.execute("""
                INSERT OR IGNORE INTO decorations (
                    id, pilotId, name, date, citation, source_file
                ) VALUES (?,?,?,?,?,?)
            """, (d.id, d.pilotId, d.name, d.date, d.citation, d.source_file))
            added_d += cursor.rowcount

        return added_m, added_v, added_d

    def get_missions_by_pilot(
        self, pilot_id: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Busca as últimas missões de um piloto."""
        with self._lock:
            conn = self._conn
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """SELECT * FROM missions WHERE pilotId = ?
                       ORDER BY date DESC, time DESC LIMIT ?""",
                    (pilot_id, limit),
                ).fetchall()
                return [dict(r) for r in rows]
            except sqlite3.Error:
                log.exception("Erro ao buscar missões")
                return []
            finally:
                conn.row_factory = None

    def count_by_pilot(self, pilot_id: str) -> int:
        """Conta missões de um piloto."""
        with self._lock:
            try:
                row = self._fetch_one(
                    "SELECT COUNT(*) FROM missions WHERE pilotId = ?",
                    (pilot_id,),
                )
                return row[0] if row else 0
            except sqlite3.Error:
                log.exception("Erro ao contar missões")
                return 0
