#!/usr/bin/env python3
"""
Repositório Base (repositories/base.py)
══════════════════════════════════════════════════════════════════
Classe base abstrata que fornece acesso à conexão SQLite thread-local
e ao lock de concorrência partilhado pelo DatabaseManager.
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import sqlite3
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..database import DatabaseManager

log = logging.getLogger("WoFFWatch")


class BaseRepository:
    """
    Classe base para todos os repositórios.
    Não deve ser usada diretamente — herdar para cada entidade.
    """

    def __init__(self, db_manager: DatabaseManager):
        self._db = db_manager

    @property
    def _conn(self) -> sqlite3.Connection:
        """Acesso direto à conexão thread-local do manager."""
        return self._db._get_conn()

    @property
    def _lock(self):
        """Acesso ao RLock partilhado do manager."""
        return self._db._lock

    def _query(
        self, sql: str, parameters: tuple = ()
    ) -> sqlite3.Cursor:
        """Executa SQL e devolve o Cursor (para INSERT/UPDATE/DELETE)."""
        return self._conn.execute(sql, parameters)

    def _fetch_one(
        self, sql: str, parameters: tuple = ()
    ) -> sqlite3.Row | None:
        """Executa SQL e devolve a primeira linha, ou None."""
        return self._conn.execute(sql, parameters).fetchone()

    def _fetch_all(
        self, sql: str, parameters: tuple = ()
    ) -> list[sqlite3.Row]:
        """Executa SQL e devolve todas as linhas."""
        return self._conn.execute(sql, parameters).fetchall()