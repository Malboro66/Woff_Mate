#!/usr/bin/env python3
"""
Módulo de Eventos e Parsers (handler.py)
══════════════════════════════════════════════════════════════════
Contém a lógica de monitorização de ficheiros (watchdog), as guardas 
de estabilidade e o roteamento para os parsers (XML, Log, TXT e Binário).

Componentes:
- FileStabilityGuard: Aguarda que o jogo termine de escrever nos ficheiros.
- WoFFEventHandler: Recebe os eventos do sistema, filtra e envia para o DatabaseManager.
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List

from watchdog.events import FileSystemEventHandler

# Importar o DatabaseManager e o CampaignEngine (Fase 2)
from database import DatabaseManager
from campaign_engine import CampaignEngine

# Importar os 4 Parsers
from parsers.xml_parser import WoFFXMLParser
from parsers.mission_log_parser import WoFFMissionLogParser
from parsers.pilot_data_parser import WoFFPilotDataParser
from parsers.dossier_parser import WoFFDossierParser

log = logging.getLogger("WoFFWatch")


# ──────────────────────────────────────────────────────────────
# GUARDIA DE ESTABILIDADE DO FICHEIRO
# ──────────────────────────────────────────────────────────────

class FileStabilityGuard:
    """
    Aguarda que o WoFF termine de escrever um ficheiro antes de fazer parse.
    O WoFF pode disparar eventos de file system enquanto ainda está a escrever,
    o que resulta em XML truncado ou texto incompleto.
    """
    def __init__(self, timeout: float = 3.0, interval: float = 0.15):
        self.timeout  = timeout
        self.interval = interval

    def wait(self, path: str) -> bool:
        if not os.path.exists(path):
            return False
        prev_size = -1
        elapsed   = 0.0
        while elapsed < self.timeout:
            try:
                size = os.path.getsize(path)
            except OSError:
                time.sleep(self.interval)
                elapsed += self.interval
                continue
            if size == prev_size and size > 0:
                log.debug(f"Ficheiro estável em {elapsed:.1f}s: {os.path.basename(path)}")
                return True
            prev_size = size
            time.sleep(self.interval)
            elapsed  += self.interval
        log.warning(f"Timeout de estabilidade ({self.timeout}s): {os.path.basename(path)}")
        return False


# ──────────────────────────────────────────────────────────────
# HANDLER DE EVENTOS COM THREADPOOL
# ──────────────────────────────────────────────────────────────

class WoFFEventHandler(FileSystemEventHandler):
    """
    Filtra e processa eventos de sistema de ficheiros do watchdog observer.
    Aguarda estabilidade do ficheiro antes de fazer parse.
    """
    
    WATCHED_EXT = {".xml", ".txt", ".log"}
    IGNORED     = {"desktop.ini", "thumbs.db", ".tmp", "~", ".bak", ".lnk"}

    def __init__(self, config, db_manager: DatabaseManager, discovery=None, pilot_id: Optional[str] = None):
        self.config    = config
        self.db_manager = db_manager
        self.discovery = discovery
        self.pilot_id  = pilot_id
        
        self.guard = FileStabilityGuard(
            timeout  = config.stability_timeout_sec,
            interval = config.stability_check_interval_sec,
        )
        
        self._pool = ThreadPoolExecutor(max_workers=config.max_workers, thread_name_prefix="woff-worker")
        self._inflight: set[str] = set()
        self._inflight_lock = threading.Lock()

    def on_modified(self, event):
        if not event.is_directory:
            self._handle(event.src_path, "modified")

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path, "created")

    def _handle(self, path: str, event_type: str):
        bn  = os.path.basename(path).lower()
        ext = os.path.splitext(path)[1].lower()
        
        if ext not in self.WATCHED_EXT:
            return
        if any(p in bn for p in self.IGNORED):
            return
            
        with self._inflight_lock:
            if path in self._inflight:
                return
            self._inflight.add(path)
            
        self._pool.submit(self._process, path, event_type)

    def _process(self, path: str, event_type: str):
        try:
            log.info(f"Detectado [{event_type}]: {os.path.basename(path)}")

            # Registra no log de descoberta se o modo estiver ativo
            if self.discovery:
                time.sleep(0.4)
                if os.path.exists(path):
                    self.discovery.log_file(path, event_type)

            # Aguarda que o ficheiro esteja completamente escrito
            if not self.guard.wait(path):
                log.warning(f"Ignorado (ficheiro instável): {os.path.basename(path)}")
                return

            # Roteia para o parser correto baseado no nome/extensão
            ext = os.path.splitext(path)[1].lower()
            if ext == ".xml":
                self._do_xml(path)
            elif ext in (".txt", ".log"):
                self._do_text(path)
                
        except Exception as e:
            log.exception(f"Erro inesperado a processar {path}: {e}")
        finally:
            # Pequena pausa para evitar reprocessar imediato de modificações encadeadas
            time.sleep(1.0)
            with self._inflight_lock:
                self._inflight.discard(path)

    def _do_xml(self, path: str):
        """Processa ficheiros XML (geralmente templates ou configurações do motor)."""
        parser = WoFFXMLParser()
        if parser.parse(path):
            self.db_manager.merge_and_write(
                pilot=parser.pilot,
                missions=parser.missions,
                victories=parser.victories,
                decorations=parser.decorations
            )

    def _do_text(self, path: str):
        """Processa ficheiros de texto (Logs, Claims, Squads, Dossier e mission.log)."""
        fname = os.path.basename(path).lower()
        
        # 1. Se for o ficheiro Dossier (Binário Ofuscado)
        if "dossier" in fname:
            parser = WoFFDossierParser()
            if parser.parse(path):
                self.db_manager.merge_and_write(
                    pilot=parser.pilot,
                    missions=[],
                    victories=[],
                    decorations=parser.decorations,
                    wingmen=parser.wingmen
                )
            return
            
        # 2. Se for um log de missão do motor do jogo (.log)
        if fname == "mission.log":
            parser = WoFFMissionLogParser()
            if parser.parse(path):
                self.db_manager.merge_and_write(
                    pilot=parser.pilot,
                    missions=[parser.mission] if parser.mission else [],
                    victories=[],
                    decorations=[]
                )
            return
            
        # 3. Restantes ficheiros de piloto (Log.txt, Claims.txt, Squads.txt)
        parser = WoFFPilotDataParser()
        if parser.parse(path):
            self.db_manager.merge_and_write(
                pilot=parser.pilot,
                missions=parser.missions, 
                victories=parser.victories,
                decorations=[]
            )
            
             # ──────────────────────────────────────────────────────────────
            # INICIAR FASE 2 (RPG ENGINE)
            # ──────────────────────────────────────────────────────────────
            # Se o parser extraiu missões, chamamos o CampaignEngine em background
            # para calcular Fadiga, Moral e gerar o Diário de Bordo.
            if parser.missions and parser.pilot and parser.pilot.name:
                pilot_name = parser.pilot.name
                mission_id = parser.missions[0].id
                
                # Submeter para a thread pool para não bloquear o watchdog
                self._pool.submit(
                    self.campaign_engine.process_mission_end, 
                    pilot_name, 
                    mission_id
                )
    def shutdown(self):
        """Encerra o pool de threads graciosamente."""
        log.info("A aguardar conclusão das threads de processamento...")
        self._pool.shutdown(wait=True)            