#!/usr/bin/env python3
"""
Repositório RPG (repositories/rpg.py)
══════════════════════════════════════════════════════════════════
Responsável por:
  - pilot_rpg_stats (UPSERT)
  - diary_entries (INSERT com deduplicação via UNIQUE constraint)
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import sqlite3
import logging
from datetime import datetime
from typing import Optional

from models import _uid
from .base import BaseRepository

log = logging.getLogger("WoFFWatch")


class RpgRepository(BaseRepository):
    """Repositório especializado em dados RPG e Diário de Bordo."""

    def update_pilot_rpg_stats(
        self, pilot_id: str, fatigue: int, morale: int, stress: int
    ) -> None:
        """Atualiza ou insere o estado RPG do piloto."""
        with self._lock:
            try:
                self._query(
                    """
                    INSERT INTO pilot_rpg_stats (
                        pilotId, fatigue, morale, stress, last_updated
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(pilotId) DO UPDATE SET
                        fatigue=excluded.fatigue,
                        morale=excluded.morale,
                        stress=excluded.stress,
                        last_updated=excluded.last_updated
                    """,
                    (pilot_id, fatigue, morale, stress, datetime.now().isoformat()),
                )
                self._conn.commit()
                log.info(
                    f"  🧠 RPG Stats: Fadiga:{fatigue} | Moral:{morale} | Stress:{stress}"
                )
            except sqlite3.Error:
                log.exception("Erro ao salvar RPG stats")
                self._conn.rollback()
                raise

    def save_diary_entry(
        self, pilot_id: str, mission_id: Optional[str], entry_date: str, narrative: str
    ) -> bool:
        """Guarda uma entrada de diário. Retorna True se inserida, False se duplicada."""
        with self._lock:
            try:
                entry_id = _uid()
                self._query(
                    """
                    INSERT INTO diary_entries (id, pilotId, missionId, entry_date, narrative)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (entry_id, pilot_id, mission_id, entry_date, narrative),
                )
                self._conn.commit()
                log.info(
                    f"  📝 Diário: missão {mission_id if mission_id else 'Evento de Vida'}."
                )
                return True
            except sqlite3.IntegrityError:
                self._conn.rollback()
                log.info(
                    f"  ⏭ Entrada duplicada ignorada: "
                    f"missão {mission_id if mission_id else 'Evento de Vida'}."
                )
                return False
            except Exception:
                log.exception("Erro ao salvar diário")
                self._conn.rollback()
                raise