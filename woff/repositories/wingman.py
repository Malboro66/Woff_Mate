#!/usr/bin/env python3
"""
Repositório de Wingmen (repositories/wingman.py)
══════════════════════════════════════════════════════════════════
Responsável por:
  - squad_members (queries)
  - wingmen_personalities (UPSERT)
  - wingmen_memory (INSERT)
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import sqlite3
import logging
from typing import Optional, List, Dict, Any

from ..models import _uid, WoFFWingman
from .base import BaseRepository

log = logging.getLogger("WoFFWatch")


class WingmanRepository(BaseRepository):
    """Repositório especializado em Wingmen AI."""

    def upsert_wingmen_batch(
        self, pilot_id: str, wingmen: Optional[List[WoFFWingman]]
    ) -> int:
        """Insere/atualiza wingmen de um piloto dentro da transação atual."""
        added_w = 0
        if not wingmen:
            return added_w

        cursor = self._conn.cursor()
        for w in wingmen:
            w.pilotId = pilot_id
            cursor.execute("""
                INSERT INTO squad_members (
                    id, pilotId, rank, fName, sName, skill, morale,
                    status, missions, flminutes, bio
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(pilotId, fName, sName) DO UPDATE SET
                    rank=excluded.rank, skill=excluded.skill,
                    morale=excluded.morale, status=excluded.status,
                    missions=excluded.missions, flminutes=excluded.flminutes,
                    bio=excluded.bio
            """, (
                w.id, w.pilotId, w.rank, w.fName, w.sName, w.skill,
                w.morale, w.status, w.missions, w.flminutes, w.bio
            ))
            added_w += cursor.rowcount
        return added_w

    def get_wingmen_by_pilot(self, pilot_id: str) -> List[Dict[str, Any]]:
        """Busca os wingmen atuais de um piloto."""
        with self._lock:
            conn = self._conn
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    "SELECT fName, sName, status FROM squad_members WHERE pilotId = ?",
                    (pilot_id,),
                ).fetchall()
                return [dict(r) for r in rows]
            except sqlite3.Error:
                log.exception("Erro ao buscar wingmen")
                return []
            finally:
                conn.row_factory = None

    def get_wingman_personality(self, wingman_id: str) -> Optional[Dict[str, Any]]:
        """Busca a personalidade 3P de um wingman."""
        with self._lock:
            conn = self._conn
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM wingmen_personalities WHERE wingmanId = ?",
                    (wingman_id,),
                ).fetchone()
                return dict(row) if row else None
            except sqlite3.Error:
                log.exception("Erro ao buscar personalidade")
                return None
            finally:
                conn.row_factory = None

    def save_wingman_personality(
        self, wingman_id: str, pilot_id: str, personality: Dict[str, Any]
    ) -> bool:
        """Guarda ou atualiza a personalidade 3P de um wingman."""
        with self._lock:
            try:
                self._query(
                    """
                    INSERT INTO wingmen_personalities (
                        wingmanId, pilotId, aerial_skill, aggression, charisma,
                        intelligence, physicality, professionalism, personality_trait
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(wingmanId) DO UPDATE SET
                        aerial_skill=excluded.aerial_skill,
                        aggression=excluded.aggression,
                        charisma=excluded.charisma,
                        intelligence=excluded.intelligence,
                        physicality=excluded.physicality,
                        professionalism=excluded.professionalism,
                        personality_trait=excluded.personality_trait
                    """,
                    (
                        wingman_id,
                        pilot_id,
                        personality.get("aerial_skill", 50),
                        personality.get("aggression", 50),
                        personality.get("charisma", 50),
                        personality.get("intelligence", 50),
                        personality.get("physicality", 50),
                        personality.get("professionalism", 50),
                        personality.get("personality_trait", "Standard"),
                    ),
                )
                self._conn.commit()
                return True
            except sqlite3.Error:
                log.exception("Erro ao salvar personalidade")
                self._conn.rollback()
                return False

    def save_wingman_memory(
        self,
        wingman_id: str,
        event_type: str,
        event_date: str,
        description: str,
        impact_morale: int = 0,
        impact_stress: int = 0,
    ) -> bool:
        """Regista um evento na memória do Wingman."""
        with self._lock:
            try:
                self._query(
                    """
                    INSERT INTO wingmen_memory (
                        id, wingmanId, event_type, event_date, description,
                        impact_morale, impact_stress
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _uid(),
                        wingman_id,
                        event_type,
                        event_date,
                        description,
                        impact_morale,
                        impact_stress,
                    ),
                )
                self._conn.commit()
                return True
            except sqlite3.Error:
                log.exception("Erro ao salvar memória")
                self._conn.rollback()
                return False
