#!/usr/bin/env python3
"""
Módulo de Eventos e Processamento (handler.py)
══════════════════════════════════════════════════════════════════
Implementa o padrão Pipeline para desacoplar a escuta de ficheiros 
do processamento de domínio (Parse, DB, RPG).
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Any

from watchdog.events import FileSystemEventHandler

from database import DatabaseManager
from campaign_engine import CampaignEngine

from parsers.xml_parser import WoFFXMLParser
from parsers.mission_log_parser import WoFFMissionLogParser
from parsers.pilot_data_parser import WoFFPilotDataParser
from parsers.dossier_parser import WoFFDossierParser

log = logging.getLogger("WoFFWatch")

class FileStabilityGuard:
    """Verifica se o ficheiro parou de crescer antes de o ler."""
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

class FileProcessor:
    """
    Pipeline de processamento de ficheiros.
    Desacopla a lógica de negócio do event handler do watchdog.
    """
    def __init__(self, db_manager: DatabaseManager, campaign_engine: CampaignEngine, discovery=None):
        self.db_manager = db_manager
        self.campaign_engine = campaign_engine
        self.discovery = discovery
        self.guard = FileStabilityGuard(timeout=3.0, interval=0.15) # Hardcoded para segurança no pipeline

    def process(self, path: str, event_type: str):
        """Executa a cadeia de processamento."""
        try:
            # 1. Estabilidade
            if not self.guard.wait(path):
                log.warning(f"Ignorado (ficheiro instável): {os.path.basename(path)}")
                return

            # 2. Discovery (Log)
            if self.discovery and os.path.exists(path):
                self.discovery.log_file(path, event_type)

            # 3. Roteamento e Parse
            ext = os.path.splitext(path)[1].lower()
            fname = os.path.basename(path).lower()

            if ext == ".xml":
                self._process_xml(path)
            elif ext in (".txt", ".log"):
                self._process_text(path, fname)
                
        except Exception as e:
            log.exception(f"Erro no pipeline de processamento para {path}: {e}")

    def _process_xml(self, path: str):
        parser = WoFFXMLParser()
        if parser.parse(path):
            # FIX: Captura o pilot_id real devolvido pelo merge.
            real_pilot_id = self.db_manager.merge_and_write(
                pilot=parser.pilot,
                missions=parser.missions,
                victories=parser.victories,
                decorations=parser.decorations
            )
            # FIX: Se houver missões e um pilot_id real, processa o fim de missão.
            if real_pilot_id and parser.missions:
                self.campaign_engine.process_mission_end(
                    real_pilot_id, parser.missions[0].id
                )

    def _process_text(self, path: str, fname: str):
        if "dossier" in fname:
            parser = WoFFDossierParser()
            if parser.parse(path) and parser.pilot:
                old_status, old_rank = self.db_manager.get_pilot_state(parser.pilot.name)
                
                # Processar Wingmen ANTES do merge
                self.campaign_engine.process_wingmen_changes(parser.pilot.name, parser.wingmen)
                
                self.db_manager.merge_and_write(
                    pilot=parser.pilot, missions=[], victories=[],
                    decorations=parser.decorations, wingmen=parser.wingmen
                )
                
                new_status = parser.pilot.status
                new_rank = parser.pilot.rank
                old_status_str = old_status if old_status is not None else ""
                old_rank_str = old_rank if old_rank is not None else ""
                
                if (old_status_str != new_status) or (old_rank_str != new_rank and new_rank):
                    self.campaign_engine.process_life_events(
                        parser.pilot.name, str(new_status), str(new_rank), old_status_str, old_rank_str
                    )
            return
            
        if fname == "mission.log":
            parser = WoFFMissionLogParser()
            if parser.parse(path):
                self.db_manager.merge_and_write(
                    pilot=parser.pilot,
                    missions=[parser.mission] if parser.mission else [],
                    victories=[], decorations=[]
                )
            return
            
        # Ficheiros de piloto (Log, Claims, Squads)
        parser = WoFFPilotDataParser()
        if parser.parse(path) and parser.pilot:
            # FIX: Usa o pilot_id real devolvido pelo merge em vez do nome placeholder.
            real_pilot_id = self.db_manager.merge_and_write(
                pilot=parser.pilot,
                missions=parser.missions, 
                victories=parser.victories,
                decorations=[]
            )
            # FIX: Só invoca o RPG se tivermos um ID real e missões.
            if real_pilot_id and parser.missions:
                self.campaign_engine.process_mission_end(
                    real_pilot_id, parser.missions[0].id
                )


class WoFFEventHandler(FileSystemEventHandler):
    """
    Listener puro do Watchdog.
    Filtra ficheiros e delega para o FileProcessor.
    """
    WATCHED_EXT = {".xml", ".txt", ".log"}
    IGNORED     = {"desktop.ini", "thumbs.db", ".tmp", "~", ".bak", ".lnk"}

    def __init__(self, config, db_manager: DatabaseManager, campaign_engine: CampaignEngine, discovery=None):
        self.config = config
        self.processor = FileProcessor(db_manager, campaign_engine, discovery)
        self._pool = ThreadPoolExecutor(max_workers=config.max_workers, thread_name_prefix="woff-worker")
        self._inflight: set[str] = set()
        self._inflight_lock = threading.Lock()

    def on_modified(self, event):
        if not event.is_directory:
            self._handle(str(event.src_path), "modified")

    def on_created(self, event):
        if not event.is_directory:
            self._handle(str(event.src_path), "created")

    def _handle(self, path: str, event_type: str):
        bn  = os.path.basename(path).lower()
        ext = os.path.splitext(path)[1].lower()
        
        if ext not in self.WATCHED_EXT or any(p in bn for p in self.IGNORED):
            return
            
        with self._inflight_lock:
            if path in self._inflight:
                return
            self._inflight.add(path)
            
        # Submete para a thread pool, chamando o processor
        self._pool.submit(self._execute_pipeline, path, event_type)

    def _execute_pipeline(self, path: str, event_type: str):
        """Método executado na thread pool."""
        try:
            log.info(f"Detectado [{event_type}]: {os.path.basename(path)}")
            self.processor.process(path, event_type)
        finally:
            with self._inflight_lock:
                self._inflight.discard(path)
            
    def shutdown(self):
        log.info("A aguardar conclusão das threads de processamento...")
        self._pool.shutdown(wait=True)