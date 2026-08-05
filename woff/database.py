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
import os
import re
import sqlite3
import time
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
            self._migration_backup_path: Optional[Path] = None
            pending_migration = self._existing_database_has_pending_migration()
            try:
                if pending_migration:
                    self._migrate_schema()
                    self._init_db()
                else:
                    self._init_db()
                    self._migrate_schema()
            except Exception:
                self._restore_migration_backup()
                raise

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
                    UNIQUE(pilotId, fName, sName),
                    FOREIGN KEY(pilotId) REFERENCES pilots(id)
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

    def _existing_database_has_pending_migration(self) -> bool:
        if not self.db_path.exists():
            return False
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            for table, cols in ALLOWED_MIGRATIONS.items():
                cursor.execute(f"PRAGMA table_info({table})")
                info = cursor.fetchall()
                existing_columns = {row[1] for row in info}
                if existing_columns and any(col not in existing_columns for col in cols):
                    return True
            return self._has_numeric_column_type_migration(cursor)
        finally:
            conn.close()

    def _backup_existing_database(self) -> Path:
        """Cria backup SQLite consistente via Connection.backup sem sobrescrever."""
        backup_dir = self.db_path.parent / ".woff-migration-backups"
        backup_dir.mkdir(exist_ok=True)
        stem = self.db_path.name
        timestamp = time.strftime("%Y%m%d%H%M%S")
        counter = 0
        while True:
            suffix = f".{counter}" if counter else ""
            backup_path = backup_dir / f"{stem}.{timestamp}{suffix}.backup.sqlite"
            try:
                fd = os.open(backup_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                counter += 1

        source: Optional[sqlite3.Connection] = None
        dest: Optional[sqlite3.Connection] = None
        try:
            source = sqlite3.connect(self.db_path)
            dest = sqlite3.connect(backup_path)
            self._run_sqlite_backup(source, dest)
            if dest.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise sqlite3.DatabaseError("integrity_check failed for migration backup")
        except Exception:
            if dest is not None:
                dest.close()
            if source is not None:
                source.close()
            try:
                backup_path.unlink()
            except FileNotFoundError:
                pass
            raise
        else:
            dest.close()
            source.close()
        self._fsync_directory(backup_dir)
        return backup_path

    def _run_sqlite_backup(self, source: sqlite3.Connection, dest: sqlite3.Connection) -> None:
        source.backup(dest)

    def _restore_migration_backup(self) -> None:
        """Restaura backup via API SQLite sem mover arquivos de conexões abertas."""
        backup_path = getattr(self, "_migration_backup_path", None)
        if backup_path is None or not backup_path.exists():
            return

        self.close()
        source = sqlite3.connect(backup_path)
        dest = sqlite3.connect(self.db_path, timeout=0)
        try:
            mode = dest.execute("PRAGMA locking_mode=EXCLUSIVE").fetchone()
            if mode is None or str(mode[0]).lower() != "exclusive":
                raise sqlite3.OperationalError("could not enable exclusive locking for restore")
            dest.execute("BEGIN EXCLUSIVE")
            dest.rollback()
            self._run_sqlite_backup(source, dest)
            if dest.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise sqlite3.DatabaseError("integrity_check failed after restoring migration backup")
        finally:
            dest.close()
            source.close()
        self._fsync_directory(self.db_path.parent)

    def _unique_sidecar_path(self, path: Path, label: str) -> Path:
        counter = 0
        while True:
            suffix = f".{counter}" if counter else ""
            candidate = path.with_name(f".{path.name}.{label}{suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        if os.name == "nt":
            return
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _migrate_schema(self):
        """
        Aplica migrações à Base de Dados se ela for de uma versão antiga.

        Riscos mitigados: o fluxo antigo desativava foreign_keys, reconstruía tabelas
        com ``CAST`` silencioso (``'abc'`` virava ``0``), descartava índices externos
        à definição da tabela e gravava ``schema_version`` no mesmo bloco que podia
        deixar uma reconstrução parcialmente aplicada. Agora a reconstrução ocorre
        dentro de transação explícita, com backup prévio, validação de inteiros,
        recriação de índices definidos pelo utilizador e verificação final por
        ``foreign_key_check`` e ``integrity_check``.

        Política para valores numéricos inválidos: NULL e string vazia são
        preservados como NULL; inteiros válidos, incluindo negativos e espaços
        em volta, são convertidos; qualquer outro valor aborta a migração com
        ValueError para não converter nem descartar dados silenciosamente.
        """
        with self._lock:
            conn = self._get_conn()
            foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            try:
                cursor = conn.cursor()
                conn.create_function("woff_safe_int", 1, self._parse_sqlite_integer)
                try:
                    cursor.execute("PRAGMA foreign_keys=OFF")
                    cursor.execute("BEGIN IMMEDIATE")
                except sqlite3.OperationalError as exc:
                    raise sqlite3.OperationalError(
                        "Cannot run schema migration because another process is writing to the database"
                    ) from exc

                cursor.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")

                def table_columns(table: str) -> set[str]:
                    cursor.execute(f"PRAGMA table_info({table})")
                    return {row[1] for row in cursor.fetchall()}

                def column_exists(table: str, col: str) -> bool:
                    return col in table_columns(table)

                pending_migration = False
                for table, cols in ALLOWED_MIGRATIONS.items():
                    existing_columns = table_columns(table)
                    if existing_columns:
                        for col in cols:
                            pending_migration = pending_migration or col not in existing_columns
                pending_migration = pending_migration or self._has_numeric_column_type_migration(cursor)
                if pending_migration and self._migration_backup_path is None:
                    self._migration_backup_path = self._backup_existing_database()

                for table, cols in ALLOWED_MIGRATIONS.items():
                    existing_columns = table_columns(table)
                    if not existing_columns:
                        continue
                    for col, typ in cols.items():
                        if col not in existing_columns:
                            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
                            log.info(f"  [Migração] Coluna '{col}' adicionada a '{table}'.")
                            existing_columns.add(col)

                self._migrate_numeric_column_types(cursor)

                if table_columns("diary_entries"):
                    cursor.execute("""
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_diary_unique_mission
                        ON diary_entries(pilotId, missionId)
                        WHERE missionId IS NOT NULL
                    """)

                if cursor.execute("PRAGMA foreign_key_check").fetchall():
                    raise sqlite3.IntegrityError("foreign_key_check failed after migration")
                if cursor.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise sqlite3.DatabaseError("integrity_check failed after migration")

                cursor.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                    (self.schema_version,)
                )
                conn.commit()
                cursor.execute(f"PRAGMA foreign_keys={foreign_keys}")
            except Exception:
                log.exception("Erro na migração de schema")
                conn.rollback()
                conn.execute(f"PRAGMA foreign_keys={foreign_keys}")
                raise

    def _numeric_columns(self) -> Dict[str, set[str]]:
        return {
            "pilots": {"missions", "flminutes", "claimsCount", "killsCount", "skill", "reputation"},
            "missions": {"enemyContacts", "claimsCount"},
            "squad_members": {"skill", "morale", "missions", "flminutes"},
        }

    def _has_numeric_column_type_migration(self, cursor: sqlite3.Cursor) -> bool:
        for table, columns in self._numeric_columns().items():
            cursor.execute(f"PRAGMA table_info({table})")
            info = cursor.fetchall()
            if any(row[1] in columns and row[2].upper() != "INTEGER" for row in info):
                return True
        return False

    def _migrate_numeric_column_types(self, cursor: sqlite3.Cursor) -> None:
        """Reconstrói tabelas antigas com colunas numéricas TEXT de forma segura."""
        for table, columns in self._numeric_columns().items():
            cursor.execute(f"PRAGMA table_info({table})")
            info = cursor.fetchall()
            if not info:
                continue
            text_numeric = [row[1] for row in info if row[1] in columns and row[2].upper() != "INTEGER"]
            if not text_numeric:
                continue

            self._validate_integer_values(cursor, table, text_numeric)
            dependent_sql = self._dependent_sql_for_table(cursor, table)
            new_table = self._unique_temp_table_name(cursor, table)
            self._create_rebuild_table_from_schema(cursor, table, new_table, text_numeric)
            self._validate_rebuild_schema(cursor, table, new_table, text_numeric)

            old_cols = [row[1] for row in info]
            cursor.execute(f"PRAGMA table_info({new_table})")
            new_cols = [row[1] for row in cursor.fetchall()]
            common_cols = [col for col in new_cols if col in old_cols]
            select_exprs = [
                self._integer_select_expression(col) if col in columns else self._quote_identifier(col)
                for col in common_cols
            ]
            column_list = ", ".join(self._quote_identifier(col) for col in common_cols)
            cursor.execute(
                f"INSERT INTO {self._quote_identifier(new_table)} ({column_list}) "
                f"SELECT {', '.join(select_exprs)} FROM {self._quote_identifier(table)}"
            )
            cursor.execute(f"DROP TABLE {self._quote_identifier(table)}")
            cursor.execute(
                f"ALTER TABLE {self._quote_identifier(new_table)} "
                f"RENAME TO {self._quote_identifier(table)}"
            )
            for sql in dependent_sql:
                cursor.execute(sql)
            log.info(
                f"  [Migração] Tabela '{table}' convertida para colunas numéricas INTEGER: "
                f"{', '.join(text_numeric)}."
            )


    def _unique_temp_table_name(self, cursor: sqlite3.Cursor, table: str) -> str:
        counter = 0
        while True:
            name = f"__woff_migration_{table}_{os.getpid()}_{time.time_ns()}_{counter}"
            cursor.execute(
                "SELECT 1 FROM sqlite_master WHERE name = ? UNION ALL "
                "SELECT 1 FROM sqlite_temp_master WHERE name = ?",
                (name, name),
            )
            if cursor.fetchone() is None:
                return name
            counter += 1

    def _create_rebuild_table_from_schema(
        self, cursor: sqlite3.Cursor, table: str, new_table: str, numeric_columns: List[str]
    ) -> None:
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ? AND sql IS NOT NULL",
            (table,),
        )
        row = cursor.fetchone()
        if row is None:
            self._create_table(cursor, table, new_table)
            return
        sql = self._rewrite_create_table_sql(row[0], table, new_table, numeric_columns)
        cursor.execute(sql)

    def _rewrite_create_table_sql(
        self, sql: str, table: str, new_table: str, numeric_columns: List[str]
    ) -> str:
        self._reject_unsupported_sql_comments(sql)
        prefix_end = self._create_table_name_end(sql)
        open_paren = sql.find("(", prefix_end)
        if open_paren == -1:
            raise ValueError(f"Unsupported CREATE TABLE format for {table}: missing column list")
        close_paren = self._matching_paren(sql, open_paren)
        definitions = self._split_top_level_csv(sql[open_paren + 1:close_paren])
        numeric_set = set(numeric_columns)
        rewritten_defs: List[str] = []
        migrated: set[str] = set()
        for definition in definitions:
            column_name = self._definition_column_name(definition)
            if column_name in numeric_set:
                rewritten_defs.append(self._rewrite_numeric_column_definition(definition, column_name))
                migrated.add(column_name)
            else:
                rewritten_defs.append(definition)
        missing = numeric_set - migrated
        if missing:
            raise ValueError(f"Unsupported CREATE TABLE format for {table}: missing columns {sorted(missing)}")
        suffix = sql[close_paren + 1:]
        return f"CREATE TABLE {self._quote_identifier(new_table)} (" + ",".join(rewritten_defs) + ")" + suffix

    @staticmethod
    def _reject_unsupported_sql_comments(sql: str) -> None:
        if "--" in sql or "/*" in sql or "*/" in sql:
            raise ValueError("Unsupported CREATE TABLE format: SQL comments are not supported")

    def _create_table_name_end(self, sql: str) -> int:
        match = re.match(
            r"\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?",
            sql,
            flags=re.IGNORECASE,
        )
        if match is None:
            raise ValueError("Unsupported CREATE TABLE format")
        index = match.end()
        _, index = self._read_identifier(sql, index)
        return index

    def _matching_paren(self, sql: str, open_paren: int) -> int:
        depth = 0
        quote: Optional[str] = None
        index = open_paren
        while index < len(sql):
            char = sql[index]
            if quote:
                if char == quote:
                    if index + 1 < len(sql) and sql[index + 1] == quote and quote in {"'", '"'}:
                        index += 2
                        continue
                    quote = None
            elif char in {"'", '"', '`'}:
                quote = char
            elif char == "[":
                quote = "]"
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
            index += 1
        raise ValueError("Unsupported CREATE TABLE format: unbalanced parentheses")

    def _split_top_level_csv(self, text: str) -> List[str]:
        parts: List[str] = []
        start = 0
        depth = 0
        quote: Optional[str] = None
        index = 0
        while index < len(text):
            char = text[index]
            if quote:
                if char == quote:
                    if index + 1 < len(text) and text[index + 1] == quote and quote in {"'", '"'}:
                        index += 2
                        continue
                    quote = None
            elif char in {"'", '"', '`'}:
                quote = char
            elif char == "[":
                quote = "]"
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                parts.append(text[start:index])
                start = index + 1
            index += 1
        parts.append(text[start:])
        return parts

    def _definition_column_name(self, definition: str) -> Optional[str]:
        stripped = definition.lstrip()
        keyword = stripped.split(None, 1)[0].upper() if stripped.split(None, 1) else ""
        if keyword in {"CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "EXCLUDE"}:
            return None
        try:
            name, _ = self._read_identifier(stripped, 0)
        except ValueError as exc:
            if "escaped delimiters" in str(exc):
                raise
            return None
        return name

    def _rewrite_numeric_column_definition(self, definition: str, column_name: str) -> str:
        leading_len = len(definition) - len(definition.lstrip())
        _, after_name = self._read_identifier(definition, leading_len)
        type_start = self._skip_space(definition, after_name)
        type_end = self._read_type_end(definition, type_start)
        column_type = definition[type_start:type_end]
        if not self._is_supported_text_type(column_type):
            raise ValueError(
                f"Unsupported numeric column type for {column_name}: {column_type!r}"
            )
        return definition[:type_start] + "INTEGER" + definition[type_end:]

    def _read_identifier(self, text: str, index: int) -> Tuple[str, int]:
        index = self._skip_space(text, index)
        if index >= len(text):
            raise ValueError("missing identifier")
        quote = text[index]
        closing = {"\"": "\"", "'": "'", "`": "`", "[": "]"}.get(quote)
        if closing:
            current = index + 1
            chars: List[str] = []
            while current < len(text):
                if text[current] == closing:
                    if current + 1 < len(text) and text[current + 1] == closing:
                        raise ValueError("Unsupported identifier: escaped delimiters are not supported")
                    return "".join(chars), current + 1
                chars.append(text[current])
                current += 1
            raise ValueError("unterminated quoted identifier")
        match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", text[index:])
        if match is None:
            raise ValueError("unsupported identifier")
        return match.group(0), index + len(match.group(0))

    @staticmethod
    def _skip_space(text: str, index: int) -> int:
        while index < len(text) and text[index].isspace():
            index += 1
        return index

    def _read_type_end(self, text: str, index: int) -> int:
        index = self._skip_space(text, index)
        if index >= len(text):
            raise ValueError("missing column type")
        depth = 0
        end = index
        while end < len(text):
            char = text[end]
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    break
                depth -= 1
            elif depth == 0 and (char.isspace() or char == ","):
                break
            end += 1
        return end

    @staticmethod
    def _is_supported_text_type(column_type: str) -> bool:
        normalized = re.sub(r"\s+", "", column_type.upper())
        return normalized in {"TEXT", "CLOB"} or bool(
            re.fullmatch(r"(?:VAR)?CHAR\(\d+\)", normalized)
        )

    def _validate_rebuild_schema(
        self, cursor: sqlite3.Cursor, table: str, new_table: str, numeric_columns: List[str]
    ) -> None:
        cursor.execute(f"PRAGMA table_info({new_table})")
        new_info = {row[1]: row for row in cursor.fetchall()}
        for column in numeric_columns:
            if new_info.get(column, (None, None, ""))[2].upper() != "INTEGER":
                raise sqlite3.DatabaseError(
                    f"Rebuilt table {table}.{column} does not have INTEGER type"
                )

        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        )
        original_sql = cursor.fetchone()[0]
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (new_table,),
        )
        rebuilt_sql = cursor.fetchone()[0]
        expected_sql = self._rewrite_create_table_sql(original_sql, table, new_table, numeric_columns)
        if self._normalize_sql(expected_sql) != self._normalize_sql(rebuilt_sql):
            raise sqlite3.DatabaseError(f"Rebuilt table {table} did not preserve schema")
        for column in numeric_columns:
            original_tail = self._column_definition_tail(original_sql, column)
            rebuilt_tail = self._column_definition_tail(rebuilt_sql, column)
            if self._normalize_sql(original_tail) != self._normalize_sql(rebuilt_tail):
                raise sqlite3.DatabaseError(
                    f"Rebuilt table {table}.{column} did not preserve column constraints"
                )

    def _column_definition_tail(self, sql: str, column: str) -> str:
        prefix_end = self._create_table_name_end(sql)
        open_paren = sql.find("(", prefix_end)
        close_paren = self._matching_paren(sql, open_paren)
        definitions = self._split_top_level_csv(sql[open_paren + 1:close_paren])
        for definition in definitions:
            if self._definition_column_name(definition) == column:
                leading_len = len(definition) - len(definition.lstrip())
                _, after_name = self._read_identifier(definition, leading_len)
                type_start = self._skip_space(definition, after_name)
                type_end = self._read_type_end(definition, type_start)
                return definition[type_end:]
        raise ValueError(f"missing column definition for {column}")

    @staticmethod
    def _normalize_sql(sql: str) -> str:
        return re.sub(r"\s+", " ", sql.strip()).upper()

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    @classmethod
    def _integer_select_expression(cls, column: str) -> str:
        quoted = cls._quote_identifier(column)
        return (
            f"CASE WHEN {quoted} IS NULL OR TRIM({quoted}) = '' THEN NULL "
            f"ELSE woff_safe_int({quoted}) END AS {quoted}"
        )

    @staticmethod
    def _parse_sqlite_integer(value: object) -> Optional[int]:
        if value is None:
            return None
        text = str(value).strip()
        if text == "":
            return None
        if not re.fullmatch(r"[+-]?[0-9]+", text):
            raise ValueError(f"invalid integer literal: {value!r}")
        integer = int(text, 10)
        if integer < -(2 ** 63) or integer > 2 ** 63 - 1:
            raise OverflowError(f"integer literal outside signed 64-bit range: {value!r}")
        return integer

    def _validate_integer_values(
        self, cursor: sqlite3.Cursor, table: str, columns: List[str]
    ) -> None:
        invalid: List[str] = []
        for column in columns:
            quoted = self._quote_identifier(column)
            cursor.execute(
                f"SELECT id, {quoted} FROM {self._quote_identifier(table)} "
                f"WHERE {quoted} IS NOT NULL AND TRIM({quoted}) != ''"
            )
            for row_id, value in cursor.fetchall():
                try:
                    self._parse_sqlite_integer(value)
                except (OverflowError, ValueError) as exc:
                    invalid.append(f"{table}.{column} id={row_id!r} value={value!r} ({exc})")
        if invalid:
            raise ValueError("Invalid integer values found during migration: " + "; ".join(invalid))

    def _dependent_sql_for_table(self, cursor: sqlite3.Cursor, table: str) -> List[str]:
        cursor.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE sql IS NOT NULL AND type = 'view' "
            "ORDER BY name"
        )
        view_rows = cursor.fetchall()
        view_names = [row[0] for row in view_rows]

        cursor.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE sql IS NOT NULL AND type IN ('index', 'trigger') "
            "ORDER BY CASE type WHEN 'index' THEN 0 ELSE 1 END, name"
        )
        object_rows = cursor.fetchall()
        table_objects = [row for row in object_rows if row[2] == table]
        view_triggers = [row for row in object_rows if row[2] in view_names]

        for name in view_names:
            cursor.execute(f"DROP VIEW IF EXISTS {self._quote_identifier(name)}")

        return (
            [row[1] for row in view_rows]
            + [row[3] for row in table_objects if row[0] == "index"]
            + [row[3] for row in table_objects if row[0] == "trigger"]
            + [row[3] for row in view_triggers]
        )

    def _create_table(self, cursor: sqlite3.Cursor, table: str, table_name: Optional[str] = None) -> None:
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
                    UNIQUE(pilotId, fName, sName),
                    FOREIGN KEY(pilotId) REFERENCES pilots(id)
                )
            """,
        }
        target_name = self._quote_identifier(table_name or table)
        statement = statements[table].replace(f"CREATE TABLE {table}", f"CREATE TABLE {target_name}", 1)
        cursor.execute(statement)

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
