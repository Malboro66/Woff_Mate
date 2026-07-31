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
from typing import List, Dict, Any

from .base import BaseRepository

log = logging.getLogger("WoFFWatch")


class MissionRepository(BaseRepository):
    """Repositório especializado na entidade WoFFMission."""

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