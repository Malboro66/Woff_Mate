#!/usr/bin/env python3
"""
Gestor de Base de Dados (database.py)
══════════════════════════════════════════════════════════════════
Responsável por armazenar e gerir os dados extraídos dos ficheiros
do WoFF BHaH II usando SQLite.

Inclui tabelas para dados do jogo (Pilotos, Missões, etc.) e 
tabelas para a camada de RPG gerada pela nossa aplicação 
(Estados RPG, Diário de Bordo).
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from dataclasses import asdict

from models import WoFFPilot, WoFFMission, WoFFVictory, WoFFDecoration, WoFFExport, WoFFWingman

log = logging.getLogger("WoFFWatch")


class DatabaseManager:
    def __init__(self, db_path: str, schema_version: str = "2.1"):
        self.db_path = Path(db_path)
        self.schema_version = schema_version
        self._lock = threading.RLock()  # SQLite precisa de controle de concorrência
        
        # Garante que a pasta existe
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Inicializa a base de dados
        with self._lock:
            self._init_db()

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
            
            # Tabela de Metadados
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # Tabela de Pilotos (Inclui campo 'photo' para a Fase 3)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pilots (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE,
                    nation TEXT,
                    rank TEXT,
                    squadron TEXT,
                    aircraft TEXT,
                    aerodrome TEXT,
                    sector TEXT,
                    startDate TEXT,
                    status TEXT,
                    notes TEXT,
                    photo TEXT,
                    source_file TEXT,
                    last_updated TEXT
                )
            """)

            # Tabela de Missões (com chave única composta para deduplicação)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS missions (
                    id TEXT PRIMARY KEY,
                    pilotId TEXT,
                    date TEXT,
                    missionType TEXT,
                    aircraft TEXT,
                    duration TEXT,
                    altitude TEXT,
                    sector TEXT,
                    weather TEXT,
                    enemyContacts TEXT,
                    claimsCount TEXT,
                    result TEXT,
                    damageReceived INTEGER,
                    woundsReceived INTEGER,
                    notes TEXT,
                    source_file TEXT,
                    UNIQUE(pilotId, date, missionType, aircraft),
                    FOREIGN KEY(pilotId) REFERENCES pilots(id)
                )
            """)

            # Tabela de Vitórias
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
                    source_file TEXT,
                    UNIQUE(pilotId, date, time, enemyType),
                    FOREIGN KEY(pilotId) REFERENCES pilots(id)
                )
            """)

            # Tabela de Condecorações
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS decorations (
                    id TEXT PRIMARY KEY,
                    pilotId TEXT,
                    name TEXT,
                    date TEXT,
                    citation TEXT,
                    source_file TEXT,
                    UNIQUE(pilotId, name),
                    FOREIGN KEY(pilotId) REFERENCES pilots(id)
                )
            """)
            
            # Tabela de Membros de Esquadrão (AI Wingmen)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS squad_members (
                    id TEXT PRIMARY KEY,
                    pilotId TEXT,
                    rank TEXT,
                    fName TEXT,
                    sName TEXT,
                    skill TEXT,
                    morale TEXT,
                    status TEXT,
                    missions TEXT,
                    flminutes TEXT,
                    bio TEXT,
                    UNIQUE(pilotId, fName, sName),
                    FOREIGN KEY(pilotId) REFERENCES pilots(id)
                )
            """)

            # Tabela de Catálogo de Medalhas
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS medals_catalog (
                    id TEXT PRIMARY KEY,
                    country TEXT,
                    name TEXT,
                    filename TEXT,
                    UNIQUE(country, name)
                )
            """)

            # Tabela de Catálogo de Esquadrões
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS squadrons (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    raw_data TEXT,
                    source_file TEXT
                )
            """)

            # ──────────────────────────────────────────────────────────────
            # TABELAS DA FASE 2 (RPG SYSTEM)
            # ──────────────────────────────────────────────────────────────

            # Tabela de Estatísticas RPG (Geradas pela nossa app)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pilot_rpg_stats (
                    pilotId TEXT PRIMARY KEY,
                    fatigue INTEGER DEFAULT 0,
                    morale INTEGER DEFAULT 75,
                    stress INTEGER DEFAULT 0,
                    last_updated TEXT,
                    FOREIGN KEY(pilotId) REFERENCES pilots(id)
                )
            """)

            # Tabela de Diário de Bordo (Narrativas geradas)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS diary_entries (
                    id TEXT PRIMARY KEY,
                    pilotId TEXT,
                    missionId TEXT,
                    entry_date TEXT,
                    narrative TEXT,
                    FOREIGN KEY(pilotId) REFERENCES pilots(id),
                    FOREIGN KEY(missionId) REFERENCES missions(id)
                )
            """)
            
            conn.commit()
            log.info(f"Base de dados SQLite pronta: {self.db_path}")
            
        except Exception as e:
            log.error(f"Erro ao inicializar base de dados: {e}")
        finally:
            conn.close()

    def merge_and_write(self,
                        pilot:       Optional[WoFFPilot],
                        missions:    List[WoFFMission],
                        victories:   List[WoFFVictory],
                        decorations: List[WoFFDecoration],
                        wingmen:     Optional[List[WoFFWingman]] = None) -> bool:
        """Faz o merge dos novos dados na base de dados SQLite."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                pilot_id = ""

                # ── Processar Piloto (UPSERT) ──
                if pilot:
                    # Verifica se o piloto já existe pelo nome
                    cursor.execute("SELECT id FROM pilots WHERE name = ?", (pilot.name,))
                    row = cursor.fetchone()
                    if row:
                        pilot_id = row[0]
                        # Atualiza os dados do piloto existente (incluindo photo)
                        cursor.execute("""
                            UPDATE pilots SET nation=?, rank=?, squadron=?, aircraft=?, aerodrome=?, 
                            sector=?, startDate=?, status=?, notes=?, photo=?, source_file=?, last_updated=?
                            WHERE id=?
                        """, (pilot.nation, pilot.rank, pilot.squadron, pilot.aircraft, pilot.aerodrome,
                              pilot.sector, pilot.startDate, pilot.status, pilot.notes, pilot.photo, 
                              pilot.source_file, pilot.last_updated, pilot_id))
                        log.info(f"  Piloto atualizado na DB: {pilot.name}")
                    else:
                        pilot_id = pilot.id
                        cursor.execute("""
                            INSERT OR IGNORE INTO pilots (id, name, nation, rank, squadron, aircraft, 
                            aerodrome, sector, startDate, status, notes, photo, source_file, last_updated)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (pilot.id, pilot.name, pilot.nation, pilot.rank, pilot.squadron, pilot.aircraft,
                              pilot.aerodrome, pilot.sector, pilot.startDate, pilot.status, pilot.notes, 
                              pilot.photo, pilot.source_file, pilot.last_updated))
                        log.info(f"  Novo piloto adicionado à DB: {pilot.name}")
                else:
                    # Se for TXT sem piloto, tenta adivinhar pelo pilotId das missões
                    pilot_id = next((m.pilotId for m in missions if m.pilotId), "")
                    if not pilot_id:
                        log.warning("  Ficheiro de debrief sem piloto associado. Ignorado.")
                        return False

                # ── Processar Missões (INSERT OR IGNORE para deduplicar) ──
                added_m = 0
                for m in missions:
                    m.pilotId = pilot_id
                    cursor.execute("""
                        INSERT OR IGNORE INTO missions (id, pilotId, date, missionType, aircraft, duration, 
                        altitude, sector, weather, enemyContacts, claimsCount, result, damageReceived, 
                        woundsReceived, notes, source_file)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (m.id, m.pilotId, m.date, m.missionType, m.aircraft, m.duration,
                          m.altitude, m.sector, m.weather, m.enemyContacts, m.claimsCount, m.result, 
                          int(m.damageReceived), int(m.woundsReceived), m.notes, m.source_file))
                    added_m += cursor.rowcount

                # ── Processar Vitórias ──
                added_v = 0
                for v in victories:
                    v.pilotId = pilot_id
                    cursor.execute("""
                        INSERT OR IGNORE INTO victories (id, pilotId, date, time, missionId, enemyType, 
                        victoryType, location, confirmed, witnesses, notes, source_file)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (v.id, v.pilotId, v.date, v.time, v.missionId, v.enemyType,
                          v.victoryType, v.location, int(v.confirmed), v.witnesses, v.notes, v.source_file))
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

                # ── Processar Membros do Esquadrão (AI Wingmen) ──
                added_w = 0
                if wingmen:
                    for w in wingmen:
                        w.pilotId = pilot_id
                        cursor.execute("""
                            INSERT OR IGNORE INTO squad_members (id, pilotId, rank, fName, sName, 
                            skill, morale, status, missions, flminutes, bio)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?)
                        """, (w.id, w.pilotId, w.rank, w.fName, w.sName, 
                              w.skill, w.morale, w.status, w.missions, w.flminutes, w.bio))
                        added_w += cursor.rowcount

                if added_m or added_v or added_d or added_w:
                    log.info(f"  + {added_m} missões, {added_v} vitórias, {added_d} condecorações, {added_w} wingmen inseridos na DB.")

                # Atualiza Metadados
                cursor.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", 
                               ("last_updated", datetime.now().isoformat()))
                cursor.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", 
                               ("schema_version", self.schema_version))

                conn.commit()
                return True
                
            except Exception as e:
                log.error(f"Erro ao escrever na base de dados: {e}")
                conn.rollback()
                return False
            finally:
                conn.close()

    # ──────────────────────────────────────────────────────────────
    # MÉTODOS DA FASE 2 (RPG SYSTEM)
    # ──────────────────────────────────────────────────────────────

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

    def save_diary_entry(self, pilot_id: str, mission_id: str, entry_date: str, narrative: str):
        """Guarda uma entrada de diário gerada pela aplicação."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                entry_id = uuid.uuid4().hex[:12]
                cursor.execute("""
                    INSERT OR IGNORE INTO diary_entries (id, pilotId, missionId, entry_date, narrative)
                    VALUES (?, ?, ?, ?, ?)
                """, (entry_id, pilot_id, mission_id, entry_date, narrative))
                conn.commit()
                log.info(f"  📝 Diário de Bordo atualizado para a missão {mission_id}.")
            except Exception as e:
                log.error(f"Erro ao salvar diário: {e}")
            finally:
                conn.close()