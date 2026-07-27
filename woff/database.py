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

import re
import logging
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Any

from models import WoFFPilot, WoFFMission, WoFFVictory, WoFFDecoration, WoFFWingman, _uid

log = logging.getLogger("WoFFWatch")


class DatabaseManager:
    def __init__(self, db_path: str, schema_version: str = "3.0"):
        self.db_path = Path(db_path)
        self.schema_version = schema_version
        self._lock = threading.RLock()  # SQLite precisa de controle de concorrência
        
        # Garante que a pasta existe
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Inicializa a base de dados
        with self._lock:
            self._init_db()
            self._migrate_schema()

    def _get_conn(self) -> sqlite3.Connection:
        """Cria uma nova ligação para a thread atual."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;") # Melhora performance em concorrência
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self):
        """Cria as tabelas se não existirem."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)""")

            # Tabela de Pilotos (Expandida com dados do Dossier, Fase 2 e 'enlisted')
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
                    missions TEXT,
                    flminutes TEXT,
                    claimsCount TEXT,
                    killsCount TEXT,
                    skill TEXT,
                    reputation TEXT,
                    source_file TEXT,
                    last_updated TEXT
                )
            """)

            # Tabela de Missões (Adicionada coluna 'time' e 'squadron')
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
                    enemyContacts TEXT,
                    claimsCount TEXT,
                    result TEXT,
                    damageReceived INTEGER,
                    woundsReceived INTEGER,
                    notes TEXT,
                    source_file TEXT,
                    UNIQUE(pilotId, date, time, missionType, aircraft),
                    FOREIGN KEY(pilotId) REFERENCES pilots(id)
                )
            """)

            # Tabela de Vitórias (Adicionado 'sector' e 'aircraft')
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

            cursor.execute("""CREATE TABLE IF NOT EXISTS decorations (
                id TEXT PRIMARY KEY, pilotId TEXT, name TEXT, date TEXT, citation TEXT, source_file TEXT,
                UNIQUE(pilotId, name), FOREIGN KEY(pilotId) REFERENCES pilots(id))""")

            cursor.execute("""CREATE TABLE IF NOT EXISTS squad_members (
                id TEXT PRIMARY KEY, pilotId TEXT, rank TEXT, fName TEXT, sName TEXT, skill TEXT, morale TEXT, 
                status TEXT, missions TEXT, flminutes TEXT, bio TEXT, UNIQUE(pilotId, fName, sName))""")

            cursor.execute("""CREATE TABLE IF NOT EXISTS medals_catalog (
                id TEXT PRIMARY KEY, country TEXT, name TEXT, filename TEXT, UNIQUE(country, name))""")

            cursor.execute("""CREATE TABLE IF NOT EXISTS squadrons (
                id TEXT PRIMARY KEY, name TEXT, raw_data TEXT, source_file TEXT)""")

            # Tabelas da Fase 2 (RPG SYSTEM)
            cursor.execute("""CREATE TABLE IF NOT EXISTS pilot_rpg_stats (
                pilotId TEXT PRIMARY KEY, fatigue INTEGER DEFAULT 0, morale INTEGER DEFAULT 75, 
                stress INTEGER DEFAULT 0, last_updated TEXT, FOREIGN KEY(pilotId) REFERENCES pilots(id))""")

            cursor.execute("""CREATE TABLE IF NOT EXISTS diary_entries (
                id TEXT PRIMARY KEY, pilotId TEXT, missionId TEXT, entry_date TEXT, narrative TEXT,
                FOREIGN KEY(pilotId) REFERENCES pilots(id), FOREIGN KEY(missionId) REFERENCES missions(id))""")
            
            # Tabelas da Fase 3 (Sistema 3P - Personalidade e Memória de Wingmen)
            cursor.execute("""CREATE TABLE IF NOT EXISTS wingmen_personalities (
                wingmanId TEXT PRIMARY KEY, 
                pilotId TEXT, 
                aerial_skill INTEGER DEFAULT 50, 
                aggression INTEGER DEFAULT 50, 
                charisma INTEGER DEFAULT 50, 
                intelligence INTEGER DEFAULT 50, 
                physicality INTEGER DEFAULT 50, 
                professionalism INTEGER DEFAULT 50,
                personality_trait TEXT, 
                FOREIGN KEY(wingmanId) REFERENCES squad_members(id)
            )""")

            cursor.execute("""CREATE TABLE IF NOT EXISTS wingmen_memory (
                id TEXT PRIMARY KEY,
                wingmanId TEXT,
                event_type TEXT,
                event_date TEXT,
                description TEXT,
                impact_morale INTEGER DEFAULT 0,
                impact_stress INTEGER DEFAULT 0,
                FOREIGN KEY(wingmanId) REFERENCES squad_members(id)
            )""")
            
            conn.commit()
            log.info(f"Base de dados SQLite pronta: {self.db_path}")
        except Exception as e:
            log.error(f"Erro ao inicializar base de dados: {e}")
        finally:
            conn.close()

    def _migrate_schema(self):
        """
        Aplica migrações à Base de Dados se ela for de uma versão antiga.
        Adiciona colunas em falta usando ALTER TABLE para não perder dados.
        """
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                
                def column_exists(table: str, col: str) -> bool:
                    cursor.execute(f"PRAGMA table_info({table})")
                    return any(row[1] == col for row in cursor.fetchall())

                # Migrações da tabela pilots
                pilots_cols = {
                    "fName": "TEXT", "sName": "TEXT", "photo": "TEXT", "birthDate": "TEXT", 
                    "birthPlace": "TEXT", "missions": "TEXT", "flminutes": "TEXT", 
                    "claimsCount": "TEXT", "killsCount": "TEXT", "skill": "TEXT", "reputation": "TEXT",
                    "enlisted": "TEXT"
                }
                for col, typ in pilots_cols.items():
                    if not column_exists("pilots", col):
                        cursor.execute(f"ALTER TABLE pilots ADD COLUMN {col} {typ}")
                        log.info(f"  [Migração] Coluna '{col}' adicionada a 'pilots'.")

                # Migrações da tabela missions
                if not column_exists("missions", "time"):
                    cursor.execute("ALTER TABLE missions ADD COLUMN time TEXT")
                    log.info("  [Migração] Coluna 'time' adicionada a 'missions'.")
                if not column_exists("missions", "squadron"):
                    cursor.execute("ALTER TABLE missions ADD COLUMN squadron TEXT")
                    log.info("  [Migração] Coluna 'squadron' adicionada a 'missions'.")

                # Migrações da tabela victories
                if not column_exists("victories", "sector"):
                    cursor.execute("ALTER TABLE victories ADD COLUMN sector TEXT")
                    log.info("  [Migração] Coluna 'sector' adicionada a 'victories'.")
                if not column_exists("victories", "aircraft"):
                    cursor.execute("ALTER TABLE victories ADD COLUMN aircraft TEXT")
                    log.info("  [Migração] Coluna 'aircraft' adicionada a 'victories'.")

                cursor.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)", (self.schema_version,))
                conn.commit()
            except Exception as e:
                log.error(f"Erro na migração de schema: {e}")
            finally:
                conn.close()

    def get_pilot_state(self, pilot_name: str):
        """Busca o status e rank atual do piloto na DB (antes de atualizar)."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT status, rank FROM pilots WHERE name = ?", (pilot_name,))
                row = cursor.fetchone()
                return (row[0], row[1]) if row else (None, None)
            except Exception as e:
                log.error(f"Erro ao buscar estado do piloto {pilot_name}: {e}")
                return None, None
            finally:
                conn.close()

    # FIX: Retorna Optional[str] com o pilot_id em vez de bool.
    #      Isso permite que o handler obtenha o ID real após o merge
    #      (essencial para invocar o CampaignEngine com o identificador correto).
    def merge_and_write(self,
                        pilot:       Optional[WoFFPilot],
                        missions:    List[WoFFMission],
                        victories:   List[WoFFVictory],
                        decorations: List[WoFFDecoration],
                        wingmen:     Optional[List[WoFFWingman]] = None) -> Optional[str]:
        """Faz o merge dos novos dados na base de dados SQLite. Retorna o pilot_id ou None."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                pilot_id = ""

                if pilot:
                    # 1. Procura pelo Nome real (vindo do Dossier)
                    cursor.execute("SELECT id FROM pilots WHERE name = ?", (pilot.name,))
                    row = cursor.fetchone()
                    
                    # 2. Se não encontrar e for um "Pilot X" genérico, procura pelo ID no source_file.
                    if not row and re.match(r"^Pilot \d+$", pilot.name):
                        pilot_num_match = re.match(r"^Pilot (\d+)$", pilot.name)
                        if pilot_num_match:
                            pilot_num = pilot_num_match.group(1)
                            glob_pattern = f"Pilot{pilot_num}[A-Za-z]*.txt"
                            cursor.execute("SELECT id FROM pilots WHERE source_file GLOB ?", (glob_pattern,))
                            row = cursor.fetchone()

                    if row:
                        pilot_id = row[0]
                        
                        # Proteção contra placeholders "Pilot X" não apagarem nomes reais
                        name_val = pilot.name
                        if re.match(r"^Pilot \d+$", name_val):
                            name_val = ""

                        # Usa COALESCE para não sobrescrever dados reais com placeholders vazios
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
                        """, (name_val, pilot.fName, pilot.sName, pilot.nation, pilot.rank, pilot.squadron, pilot.aircraft, 
                              pilot.aerodrome, pilot.sector, pilot.startDate, pilot.enlisted, pilot.status, pilot.notes, pilot.photo, 
                              pilot.birthDate, pilot.birthPlace, pilot.missions, pilot.flminutes, pilot.claimsCount, 
                              pilot.killsCount, pilot.skill, pilot.reputation, pilot.source_file, pilot.last_updated, pilot_id))
                        log.info(f"  Piloto atualizado na DB: ID {pilot_id}")
                    else:
                        pilot_id = pilot.id
                        cursor.execute("""
                            INSERT OR IGNORE INTO pilots (id, name, fName, sName, nation, rank, squadron, aircraft, aerodrome, 
                            sector, startDate, enlisted, status, notes, photo, birthDate, birthPlace, missions, flminutes, claimsCount, 
                            killsCount, skill, reputation, source_file, last_updated)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (pilot.id, pilot.name, pilot.fName, pilot.sName, pilot.nation, pilot.rank, pilot.squadron, pilot.aircraft, 
                              pilot.aerodrome, pilot.sector, pilot.startDate, pilot.enlisted, pilot.status, pilot.notes, pilot.photo, 
                              pilot.birthDate, pilot.birthPlace, pilot.missions, pilot.flminutes, pilot.claimsCount, 
                              pilot.killsCount, pilot.skill, pilot.reputation, pilot.source_file, pilot.last_updated))
                        log.info(f"  Novo piloto adicionado à DB: {pilot.name}")
                else:
                    # Se pilot for None, resolve o UUID baseado no source_file das missões/vitórias
                    source_file = next((m.source_file for m in missions if m.source_file), None)
                    if not source_file and victories:
                        source_file = next((v.source_file for v in victories if v.source_file), None)
                        
                    if source_file:
                        pilot_num_match = re.match(r"^Pilot(\d+)", os.path.basename(source_file), re.I)
                        if pilot_num_match:
                            pilot_num = pilot_num_match.group(1)
                            glob_pattern = f"Pilot{pilot_num}[A-Za-z]*.txt"
                            cursor.execute("SELECT id FROM pilots WHERE source_file GLOB ?", (glob_pattern,))
                            row = cursor.fetchone()
                            if row:
                                pilot_id = row[0]

                if not pilot_id:
                    pilot_id = next((m.pilotId for m in missions if m.pilotId), "")
                    if not pilot_id:
                        log.warning("  Ficheiro de debrief sem piloto associado. Ignorado.")
                        return None

                # ── Processar Missões (com squadron e time) ──
                added_m = 0
                for m in missions:
                    m.pilotId = pilot_id
                    cursor.execute("""
                        INSERT OR IGNORE INTO missions (id, pilotId, date, time, missionType, aircraft, duration, altitude, 
                        sector, squadron, weather, enemyContacts, claimsCount, result, damageReceived, woundsReceived, notes, source_file)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (m.id, m.pilotId, m.date, m.time, m.missionType, m.aircraft, m.duration, m.altitude, m.sector, 
                          m.squadron, m.weather, m.enemyContacts, m.claimsCount, m.result, int(m.damageReceived), int(m.woundsReceived), 
                          m.notes, m.source_file))
                    added_m += cursor.rowcount

                # ── Processar Vitórias (com sector e aircraft) ──
                added_v = 0
                for v in victories:
                    v.pilotId = pilot_id
                    cursor.execute("""
                        INSERT OR IGNORE INTO victories (id, pilotId, date, time, missionId, enemyType, victoryType, location, 
                        confirmed, witnesses, notes, sector, aircraft, source_file)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (v.id, v.pilotId, v.date, v.time, v.missionId, v.enemyType,
                          v.victoryType, v.location, int(v.confirmed), v.witnesses, v.notes, 
                          v.sector, v.aircraft, v.source_file))
                    added_v += cursor.rowcount

                # ── Processar Condecorações ──
                added_d = 0
                for d in decorations:
                    d.pilotId = pilot_id
                    cursor.execute("""
                        INSERT OR IGNORE INTO decorations (id, pilotId, name, date, citation, source_file)
                        VALUES (?,?,?,?,?,?)
                    """, (d.id, d.pilotId, d.name, d.date, d.citation, d.source_file))
                    added_d += cursor.rowcount

                # ── Processar Membros do Esquadrão (AI Wingmen com UPSERT) ──
                added_w = 0
                if wingmen:
                    for w in wingmen:
                        w.pilotId = pilot_id
                        # FIX: Usar UPSERT para atualizar o status se o wingman já existir (ex: passou a Wounded/KIA)
                        cursor.execute("""
                            INSERT INTO squad_members (id, pilotId, rank, fName, sName, 
                            skill, morale, status, missions, flminutes, bio)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?)
                            ON CONFLICT(pilotId, fName, sName) DO UPDATE SET 
                                rank=excluded.rank, 
                                skill=excluded.skill, 
                                morale=excluded.morale, 
                                status=excluded.status, 
                                missions=excluded.missions, 
                                flminutes=excluded.flminutes, 
                                bio=excluded.bio
                        """, (w.id, w.pilotId, w.rank, w.fName, w.sName, 
                              w.skill, w.morale, w.status, w.missions, w.flminutes, w.bio))
                        added_w += cursor.rowcount

                if added_m or added_v or added_d or added_w:
                    log.info(f"  + {added_m} missões, {added_v} vitórias, {added_d} condecorações, {added_w} wingmen inseridos.")

                cursor.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_updated', ?)", (datetime.now().isoformat(),))
                conn.commit()
                return pilot_id
                
            except Exception as e:
                log.error(f"Erro ao escrever na base de dados: {e}")
                conn.rollback()
                return None
            finally:
                conn.close()

    # ──────────────────────────────────────────────────────────────
    # MÉTODOS DA FASE 2 E 3 (RPG SYSTEM & 3P PROFILES)
    # ──────────────────────────────────────────────────────────────

    def get_pilot_id_by_name(self, pilot_name: str) -> Optional[str]:
        """Busca o ID do piloto pelo nome de forma segura."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM pilots WHERE name = ?", (pilot_name,))
                row = cursor.fetchone()
                return row[0] if row else None
            except Exception as e:
                log.error(f"Erro ao buscar ID do piloto {pilot_name}: {e}")
                return None
            finally:
                conn.close()

    def get_wingmen_by_pilot(self, pilot_id: str) -> List[dict]:
        """Busca os wingmen atuais de um piloto na DB para comparação de status."""
        with self._lock:
            conn = self._get_conn()
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute("SELECT fName, sName, status FROM squad_members WHERE pilotId = ?", (pilot_id,))
                return [dict(row) for row in cursor.fetchall()]
            except Exception as e:
                log.error(f"Erro ao buscar wingmen: {e}")
                return []
            finally:
                conn.close()

    def get_mission_and_history(self, pilot_identifier: str, mission_id: str):
        """Busca o piloto, a missão EXATA e o histórico de missões."""
        with self._lock:
            conn = self._get_conn()
            conn.row_factory = sqlite3.Row
            try:
                pilot = conn.execute(
                    "SELECT * FROM pilots WHERE id = ? OR name = ?", 
                    (pilot_identifier, pilot_identifier)
                ).fetchone()
                if not pilot: return None, None, []
                    
                current_mission = conn.execute(
                    "SELECT * FROM missions WHERE id = ? AND pilotId = ?", 
                    (mission_id, pilot["id"])
                ).fetchone()
                if not current_mission: return dict(pilot), None, []
                    
                history = conn.execute(
                    "SELECT * FROM missions WHERE pilotId = ? ORDER BY date DESC, time DESC LIMIT 10", 
                    (pilot["id"],)
                ).fetchall()
                return dict(pilot), dict(current_mission), [dict(m) for m in history]
            except Exception as e:
                log.error(f"Erro ao buscar missão/histórico: {e}")
                return None, None, []
            finally:
                conn.close()

    # FIX: Novo método que devolve a data mais recente do piloto (última missão ou startDate),
    #      evitando que o CampaignEngine use datetime.now() (2026) no diário.
    def get_pilot_game_date(self, pilot_id: str) -> str:
        """Busca a data mais recente do piloto (missão mais recente ou startDate)."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT date FROM missions WHERE pilotId = ? ORDER BY date DESC LIMIT 1",
                    (pilot_id,)
                )
                row = cursor.fetchone()
                if row and row[0]:
                    return row[0]
                cursor.execute("SELECT startDate FROM pilots WHERE id = ?", (pilot_id,))
                row = cursor.fetchone()
                if row and row[0]:
                    return row[0]
                return "1917-01-01"
            except Exception as e:
                log.error(f"Erro ao buscar data do jogo: {e}")
                return "1917-01-01"
            finally:
                conn.close()

    def update_pilot_rpg_stats(self, pilot_id: str, fatigue: int, morale: int, stress: int):
        """Atualiza ou insere o estado RPG do piloto na Base de Dados."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO pilot_rpg_stats (pilotId, fatigue, morale, stress, last_updated)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(pilotId) DO UPDATE SET 
                        fatigue=excluded.fatigue, 
                        morale=excluded.morale, 
                        stress=excluded.stress, 
                        last_updated=excluded.last_updated
                """, (pilot_id, fatigue, morale, stress, datetime.now().isoformat()))
                conn.commit()
                log.info(f"  🧠 RPG Stats atualizados: Fadiga:{fatigue} | Moral:{morale} | Stress:{stress}")
            except Exception as e:
                log.error(f"Erro ao salvar RPG stats: {e}")
            finally:
                conn.close()

    def save_diary_entry(self, pilot_id: str, mission_id: Optional[str], entry_date: str, narrative: str):
        """Guarda uma entrada de diário gerada pela aplicação."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                entry_id = _uid()
                cursor.execute("""
                    INSERT OR IGNORE INTO diary_entries (id, pilotId, missionId, entry_date, narrative)
                    VALUES (?, ?, ?, ?, ?)
                """, (entry_id, pilot_id, mission_id, entry_date, narrative))
                conn.commit()
                log.info(f"  📝 Diário de Bordo atualizado para a missão {mission_id if mission_id else 'Evento de Vida'}.")
            except Exception as e:
                log.error(f"Erro ao salvar diário: {e}")
            finally:
                conn.close()

    # ── 3P System: Personalidade e Memória ──

    def get_wingman_personality(self, wingman_id: str) -> Optional[dict]:
        """Busca a personalidade 3P de um wingman."""
        with self._lock:
            conn = self._get_conn()
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute("SELECT * FROM wingmen_personalities WHERE wingmanId = ?", (wingman_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
            except Exception as e:
                log.error(f"Erro ao buscar personalidade: {e}")
                return None
            finally:
                conn.close()

    def save_wingman_personality(self, wingman_id: str, pilot_id: str, personality: dict) -> bool:
        """Guarda ou atualiza a personalidade 3P de um wingman."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO wingmen_personalities (wingmanId, pilotId, aerial_skill, aggression, charisma, intelligence, physicality, professionalism, personality_trait)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(wingmanId) DO UPDATE SET 
                        aerial_skill=excluded.aerial_skill, 
                        aggression=excluded.aggression, 
                        charisma=excluded.charisma, 
                        intelligence=excluded.intelligence, 
                        physicality=excluded.physicality, 
                        professionalism=excluded.professionalism, 
                        personality_trait=excluded.personality_trait
                """, (wingman_id, pilot_id, personality.get("aerial_skill", 50), personality.get("aggression", 50), 
                       personality.get("charisma", 50), personality.get("intelligence", 50), 
                       personality.get("physicality", 50), personality.get("professionalism", 50), personality.get("personality_trait", "Standard")))
                conn.commit()
                return True
            except Exception as e:
                log.error(f"Erro ao salvar personalidade: {e}")
                return False
            finally:
                conn.close()

    def save_wingman_memory(self, wingman_id: str, event_type: str, event_date: str, description: str, impact_morale: int = 0, impact_stress: int = 0) -> bool:
        """Regista um evento na memória do Wingman."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO wingmen_memory (id, wingmanId, event_type, event_date, description, impact_morale, impact_stress)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (_uid(), wingman_id, event_type, event_date, description, impact_morale, impact_stress))
                conn.commit()
                return True
            except Exception as e:
                log.error(f"Erro ao salvar memória: {e}")
                return False
            finally:
                conn.close()