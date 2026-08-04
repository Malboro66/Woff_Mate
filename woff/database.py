#!/usr/bin/env python3
"""
Gestor de Base de Dados (database.py)
══════════════════════════════════════════════════════════════════
Responsável por armazenar e gerir os dados extraídos dos ficheiros
do WoFF BHaH II usando SQLite.

Inclui tabelas para dados do jogo (Pilotos, Missões, etc.), 
tabelas para a camada de RPG (Estados, Diário) e tabelas para 
o Sistema 3P (Personalidades e Memória de Wingmen).
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Any, Dict, Tuple

from .models import WoFFPilot, WoFFMission, WoFFVictory, WoFFDecoration, WoFFWingman
from .repositories import PilotRepository, MissionRepository, RpgRepository, WingmanRepository

log = logging.getLogger("WoFFWatch")

# ── Whitelist de migrações schema (proteção contra SQL Injection) ──
ALLOWED_MIGRATIONS: Dict[str, Dict[str, str]] = {
    "pilots": {
        "fName": "TEXT", "sName": "TEXT", "photo": "TEXT", "birthDate": "TEXT",
        "birthPlace": "TEXT", "missions": "INTEGER", "flminutes": "INTEGER",
        "claimsCount": "INTEGER", "killsCount": "INTEGER", "skill": "INTEGER", "reputation": "INTEGER",
        "enlisted": "TEXT"
    },
    "missions": {
        "time": "TEXT", "squadron": "TEXT", "enemyContacts": "INTEGER",
        "claimsCount": "INTEGER"
    },
    "squad_members": {
        "skill": "INTEGER", "morale": "INTEGER", "missions": "INTEGER",
        "flminutes": "INTEGER"
    },
    "victories": {
        "sector": "TEXT", "aircraft": "TEXT"
    }
}


class DatabaseManager:
    def __init__(self, db_path: str, schema_version: str = "3.1"):
        self.db_path = Path(db_path)
        self.schema_version = schema_version
        self._lock = threading.RLock()
        self._local = threading.local()

        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            self._init_db()
            self._migrate_schema()

        self._pilots = PilotRepository(self)
        self._missions = MissionRepository(self)
        self._rpg = RpgRepository(self)
        self._wingmen = WingmanRepository(self)

    # ── Thread-Local Connection Pooling ──
    def _open_conn(self) -> sqlite3.Connection:
        """Cria uma conexão SQLite com todas as opções exigidas pelo gestor."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _get_conn(self) -> sqlite3.Connection:
        """Devolve a conexão da thread atual, recriando-a se tiver sido fechada."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = self._open_conn()
            return self._local.conn

        try:
            self._local.conn.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            self._local.conn = self._open_conn()

        return self._local.conn

    def close(self) -> None:
        """Fecha a conexão da thread atual. Chamar no shutdown."""
        if hasattr(self._local, 'conn') and self._local.conn:
            try:
                self._local.conn.close()
            finally:
                self._local.conn = None

    def _init_db(self):
        """Cria as tabelas se não existirem."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()

            cursor.execute(
                "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
            )

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pilots (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE,
                    fName TEXT,
                    sName TEXT,
                    nation TEXT,
                    rank TEXT,
                    squadron TEXT,
                    aircraft TEXT,
                    aerodrome TEXT,
                    sector TEXT,
                    startDate TEXT,
                    enlisted TEXT,
                    status TEXT,
                    notes TEXT,
                    photo TEXT,
                    birthDate TEXT,
                    birthPlace TEXT,
                    missions INTEGER,
                    flminutes INTEGER,
                    claimsCount INTEGER,
                    killsCount INTEGER,
                    skill INTEGER,
                    reputation INTEGER,
                    source_file TEXT,
                    last_updated TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS missions (
                    id TEXT PRIMARY KEY,
                    pilotId TEXT,
                    date TEXT,
                    time TEXT,
                    missionType TEXT,
                    aircraft TEXT,
                    duration TEXT,
                    altitude TEXT,
                    sector TEXT,
                    squadron TEXT,
                    weather TEXT,
                    enemyContacts INTEGER,
                    claimsCount INTEGER,
                    result TEXT,
                    damageReceived INTEGER,
                    woundsReceived INTEGER,
                    notes TEXT,
                    source_file TEXT,
                    UNIQUE(pilotId, date, time, missionType, aircraft),
                    FOREIGN KEY(pilotId) REFERENCES pilots(id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS victories (
                    id TEXT PRIMARY KEY,
                    pilotId TEXT,
                    date TEXT,
                    time TEXT,
                    missionId TEXT,
                    enemyType TEXT,
                    victoryType TEXT,
                    location TEXT,
                    confirmed INTEGER,
                    witnesses TEXT,
                    notes TEXT,
                    sector TEXT,
                    aircraft TEXT,
                    source_file TEXT,
                    UNIQUE(pilotId, date, time, enemyType),
                    FOREIGN KEY(pilotId) REFERENCES pilots(id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS decorations (
                    id TEXT PRIMARY KEY, pilotId TEXT, name TEXT, date TEXT,
                    citation TEXT, source_file TEXT,
                    UNIQUE(pilotId, name), FOREIGN KEY(pilotId) REFERENCES pilots(id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS squad_members (
                    id TEXT PRIMARY KEY, pilotId TEXT, rank TEXT, fName TEXT,
                    sName TEXT, skill INTEGER, morale INTEGER, status TEXT, missions INTEGER,
                    flminutes INTEGER, bio TEXT,
                    UNIQUE(pilotId, fName, sName)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS medals_catalog (
                    id TEXT PRIMARY KEY, country TEXT, name TEXT, filename TEXT,
                    UNIQUE(country, name)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS squadrons (
                    id TEXT PRIMARY KEY, name TEXT, raw_data TEXT, source_file TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pilot_rpg_stats (
                    pilotId TEXT PRIMARY KEY, fatigue INTEGER DEFAULT 0,
                    morale INTEGER DEFAULT 75, stress INTEGER DEFAULT 0,
                    last_updated TEXT,
                    FOREIGN KEY(pilotId) REFERENCES pilots(id)
                )
            """)

            # FIX: UNIQUE parcial para permitir múltiplos eventos de vida (missionId=NULL)
            # mas bloquear missões duplicadas no diário.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS diary_entries (
                    id TEXT PRIMARY KEY,
                    pilotId TEXT NOT NULL,
                    missionId TEXT,
                    entry_date TEXT,
                    narrative TEXT,
                    FOREIGN KEY(pilotId) REFERENCES pilots(id),
                    FOREIGN KEY(missionId) REFERENCES missions(id)
                )
            """)
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_diary_unique_mission
                ON diary_entries(pilotId, missionId)
                WHERE missionId IS NOT NULL
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS wingmen_personalities (
                    wingmanId TEXT PRIMARY KEY, pilotId TEXT,
                    aerial_skill INTEGER DEFAULT 50, aggression INTEGER DEFAULT 50,
                    charisma INTEGER DEFAULT 50, intelligence INTEGER DEFAULT 50,
                    physicality INTEGER DEFAULT 50, professionalism INTEGER DEFAULT 50,
                    personality_trait TEXT,
                    FOREIGN KEY(wingmanId) REFERENCES squad_members(id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS wingmen_memory (
                    id TEXT PRIMARY KEY, wingmanId TEXT, event_type TEXT,
                    event_date TEXT, description TEXT, impact_morale INTEGER DEFAULT 0,
                    impact_stress INTEGER DEFAULT 0,
                    FOREIGN KEY(wingmanId) REFERENCES squad_members(id)
                )
            """)

            conn.commit()
            log.info(f"Base de dados SQLite pronta: {self.db_path}")
        except Exception:
            log.exception("Erro ao inicializar base de dados")
            raise
        # Nota: não fechamos conn aqui — thread-local permanece aberta

    def _migrate_schema(self):
        """
        Aplica migrações à Base de Dados se ela for de uma versão antiga.
        Usa whitelist rígida para evitar SQL Injection.
        """
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("PRAGMA foreign_keys=OFF")

                def column_exists(table: str, col: str) -> bool:
                    cursor.execute(f"PRAGMA table_info({table})")
                    return any(row[1] == col for row in cursor.fetchall())

                for table, cols in ALLOWED_MIGRATIONS.items():
                    for col, typ in cols.items():
                        if not column_exists(table, col):
                            # Whitelist garante que col e typ são seguros
                            cursor.execute(
                                f"ALTER TABLE {table} ADD COLUMN {col} {typ}"
                            )
                            log.info(
                                f"  [Migração] Coluna '{col}' adicionada a '{table}'."
                            )


                self._migrate_numeric_column_types(cursor)

                # Migração do índice único do diário (para bases antigas)
                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_diary_unique_mission
                    ON diary_entries(pilotId, missionId)
                    WHERE missionId IS NOT NULL
                """)

                cursor.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                    (self.schema_version,)
                )
                conn.commit()
                cursor.execute("PRAGMA foreign_keys=ON")
            except Exception:
                log.exception("Erro na migração de schema")
                conn.rollback()
                conn.execute("PRAGMA foreign_keys=ON")
                raise

    def _migrate_numeric_column_types(self, cursor: sqlite3.Cursor) -> None:
        """Rebuild old tables whose numeric columns were created as TEXT."""
        numeric_columns = {
            "pilots": {"missions", "flminutes", "claimsCount", "killsCount", "skill", "reputation"},
            "missions": {"enemyContacts", "claimsCount"},
            "squad_members": {"skill", "morale", "missions", "flminutes"},
        }

        for table, columns in numeric_columns.items():
            cursor.execute(f"PRAGMA table_info({table})")
            info = cursor.fetchall()
            if not info:
                continue
            text_numeric = [row[1] for row in info if row[1] in columns and row[2].upper() != "INTEGER"]
            if not text_numeric:
                continue

            old_table = f"{table}__text_backup"
            cursor.execute(f"DROP TABLE IF EXISTS {old_table}")
            cursor.execute(f"ALTER TABLE {table} RENAME TO {old_table}")
            self._create_table(cursor, table)

            old_cols = [row[1] for row in info]
            cursor.execute(f"PRAGMA table_info({table})")
            new_cols = [row[1] for row in cursor.fetchall()]
            common_cols = [col for col in new_cols if col in old_cols]
            select_exprs = [
                f"CAST(NULLIF({col}, '') AS INTEGER) AS {col}" if col in columns else col
                for col in common_cols
            ]
            cursor.execute(
                f"INSERT INTO {table} ({', '.join(common_cols)}) "
                f"SELECT {', '.join(select_exprs)} FROM {old_table}"
            )
            cursor.execute(f"DROP TABLE {old_table}")
            log.info(
                f"  [Migração] Tabela '{table}' convertida para colunas numéricas INTEGER: "
                f"{', '.join(text_numeric)}."
            )

    def _create_table(self, cursor: sqlite3.Cursor, table: str) -> None:
        statements = {
            "pilots": """
                CREATE TABLE pilots (
                    id TEXT PRIMARY KEY, name TEXT UNIQUE, fName TEXT, sName TEXT,
                    nation TEXT, rank TEXT, squadron TEXT, aircraft TEXT,
                    aerodrome TEXT, sector TEXT, startDate TEXT, enlisted TEXT,
                    status TEXT, notes TEXT, photo TEXT, birthDate TEXT,
                    birthPlace TEXT, missions INTEGER, flminutes INTEGER,
                    claimsCount INTEGER, killsCount INTEGER, skill INTEGER,
                    reputation INTEGER, source_file TEXT, last_updated TEXT
                )
            """,
            "missions": """
                CREATE TABLE missions (
                    id TEXT PRIMARY KEY, pilotId TEXT, date TEXT, time TEXT,
                    missionType TEXT, aircraft TEXT, duration TEXT, altitude TEXT,
                    sector TEXT, squadron TEXT, weather TEXT, enemyContacts INTEGER,
                    claimsCount INTEGER, result TEXT, damageReceived INTEGER,
                    woundsReceived INTEGER, notes TEXT, source_file TEXT,
                    UNIQUE(pilotId, date, time, missionType, aircraft),
                    FOREIGN KEY(pilotId) REFERENCES pilots(id)
                )
            """,
            "squad_members": """
                CREATE TABLE squad_members (
                    id TEXT PRIMARY KEY, pilotId TEXT, rank TEXT, fName TEXT,
                    sName TEXT, skill INTEGER, morale INTEGER, status TEXT,
                    missions INTEGER, flminutes INTEGER, bio TEXT,
                    UNIQUE(pilotId, fName, sName)
                )
            """,
        }
        cursor.execute(statements[table])

    def get_pilot_state(self, pilot_name: str) -> Tuple[Optional[str], Optional[str]]:
        return self._pilots.get_pilot_state(pilot_name)

    def resolve_pilot_id(
        self, name: str, source_file: Optional[str] = None
    ) -> Optional[str]:
        return self._pilots.resolve_pilot_id(name, source_file)

    def merge_and_write(
        self,
        pilot: Optional[WoFFPilot],
        missions: List[WoFFMission],
        victories: List[WoFFVictory],
        decorations: List[WoFFDecoration],
        wingmen: Optional[List[WoFFWingman]] = None
    ) -> Optional[str]:
        """Faz o merge dos novos dados na base de dados SQLite. Retorna o pilot_id ou None."""
        with self._lock:
            conn = self._get_conn()
            try:
                pilot_id = self._pilots.upsert_pilot(pilot, missions, victories)
                if not pilot_id:
                    return None
                added_m, added_v, added_d = self._missions.upsert_mission(
                    pilot_id, missions, victories, decorations
                )
                added_w = self._wingmen.upsert_wingmen_batch(pilot_id, wingmen)
                if added_m or added_v or added_d or added_w:
                    log.info(
                        f"  + {added_m} missões, {added_v} vitórias, {added_d} "
                        f"condecorações, {added_w} wingmen inseridos."
                    )
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_updated', ?)",
                    (datetime.now().isoformat(),)
                )
                conn.commit()
                return pilot_id
            except sqlite3.IntegrityError as e:
                log.error(f"Erro de integridade na base de dados: {e}")
                conn.rollback()
                return None
            except Exception:
                log.exception("Erro ao escrever na base de dados")
                conn.rollback()
                raise

    def get_pilot_id_by_name(self, pilot_name: str) -> Optional[str]:
        return self._pilots.get_pilot_id_by_name(pilot_name)

    def get_wingmen_by_pilot(self, pilot_id: str) -> List[dict]:
        return self._wingmen.get_wingmen_by_pilot(pilot_id)

    def get_mission_and_history(
        self, pilot_identifier: str, mission_id: str
    ) -> Tuple[Optional[dict], Optional[dict], List[dict]]:
        return self._pilots.get_mission_and_history(pilot_identifier, mission_id)

    def get_pilot_game_date(self, pilot_id: str) -> str:
        return self._pilots.get_pilot_game_date(pilot_id)

    def update_pilot_rpg_stats(
        self, pilot_id: str, fatigue: int, morale: int, stress: int
    ) -> None:
        return self._rpg.update_pilot_rpg_stats(pilot_id, fatigue, morale, stress)

    def save_diary_entry(
        self, pilot_id: str, mission_id: Optional[str], entry_date: str, narrative: str
    ) -> bool:
        return self._rpg.save_diary_entry(pilot_id, mission_id, entry_date, narrative)

    def get_wingman_personality(self, wingman_id: str) -> Optional[dict]:
        return self._wingmen.get_wingman_personality(wingman_id)

    def save_wingman_personality(
        self, wingman_id: str, pilot_id: str, personality: dict
    ) -> bool:
        return self._wingmen.save_wingman_personality(wingman_id, pilot_id, personality)

    def save_wingman_memory(
        self, wingman_id: str, event_type: str, event_date: str,
        description: str, impact_morale: int = 0, impact_stress: int = 0
    ) -> bool:
        return self._wingmen.save_wingman_memory(
            wingman_id, event_type, event_date, description, impact_morale, impact_stress
        )
