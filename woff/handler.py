#!/usr/bin/env python3
"""
Módulo de Eventos e Parsers (handler.py)
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

from database import DatabaseManager
from campaign_engine import CampaignEngine

from parsers.xml_parser import WoFFXMLParser
from parsers.mission_log_parser import WoFFMissionLogParser
from parsers.pilot_data_parser import WoFFPilotDataParser
from parsers.dossier_parser import WoFFDossierParser

log = logging.getLogger("WoFFWatch")

class FileStabilityGuard:
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
                return True
            prev_size = size
            time.sleep(self.interval)
            elapsed  += self.interval
        log.warning(f"Timeout de estabilidade ({self.timeout}s): {os.path.basename(path)}")
        return False


class WoFFEventHandler(FileSystemEventHandler):
    WATCHED_EXT = {".xml", ".txt", ".log"}
    IGNORED     = {"desktop.ini", "thumbs.db", ".tmp", "~", ".bak", ".lnk"}

    def __init__(self, config, db_manager: DatabaseManager, campaign_engine: CampaignEngine, discovery=None, pilot_id: Optional[str] = None):
        self.config    = config
        self.db_manager = db_manager
        self.campaign_engine = campaign_engine
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
            # FIX: Garantir que o caminho é string (watchdog pode enviar bytes em alguns SOs)
            self._handle(str(event.src_path), "modified")

    def on_created(self, event):
        if not event.is_directory:
            self._handle(str(event.src_path), "created")

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

            if not self.guard.wait(path):
                log.warning(f"Ignorado (ficheiro instável): {os.path.basename(path)}")
                return

            if self.discovery:
                if os.path.exists(path):
                    self.discovery.log_file(path, event_type)

            ext = os.path.splitext(path)[1].lower()
            if ext == ".xml":
                self._do_xml(path)
            elif ext in (".txt", ".log"):
                self._do_text(path)
                
        except Exception as e:
            log.exception(f"Erro inesperado a processar {path}: {e}")
        finally:
            with self._inflight_lock:
                self._inflight.discard(path)

    def _do_xml(self, path: str):
        parser = WoFFXMLParser()
        if parser.parse(path):
            self.db_manager.merge_and_write(
                pilot=parser.pilot,
                missions=parser.missions,
                victories=parser.victories,
                decorations=parser.decorations
            )

    def _do_text(self, path: str):
        fname = os.path.basename(path).lower()
        
        if "dossier" in fname:
            parser = WoFFDossierParser()
            if parser.parse(path):
                # FIX: Verificar se o piloto não é None antes de aceder aos atributos
                if not parser.pilot: return
                
                old_status, old_rank = self.db_manager.get_pilot_state(parser.pilot.name)
                self.db_manager.merge_and_write(
                    pilot=parser.pilot,
                    missions=[],
                    victories=[],
                    decorations=parser.decorations,
                    wingmen=parser.wingmen
                )
                new_status = parser.pilot.status
                new_rank = parser.pilot.rank
                
                # FIX: Tratar os retornos Optional[str] do get_pilot_state
                old_status_str = old_status if old_status is not None else ""
                old_rank_str = old_rank if old_rank is not None else ""
                
                if (old_status_str != new_status) or (old_rank_str != new_rank and new_rank):
                    self._pool.submit(
                        self.campaign_engine.process_life_events,
                        parser.pilot.name, 
                        str(new_status), 
                        str(new_rank), 
                        old_status_str, 
                        old_rank_str
                    )
            return
            
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
            
        parser = WoFFPilotDataParser()
        if parser.parse(path):
            # FIX: Verificar se o piloto não é None antes de aceder aos atributos
            if not parser.pilot: return
            
            self.db_manager.merge_and_write(
                pilot=parser.pilot,
                missions=parser.missions, 
                victories=parser.victories,
                decorations=[]
            )
            if parser.missions and parser.pilot.name:
                pilot_name = parser.pilot.name
                mission_id = parser.missions[0].id
                self._pool.submit(
                    self.campaign_engine.process_mission_end,
                    pilot_name, mission_id
                )
            
    def shutdown(self):
        log.info("A aguardar conclusão das threads de processamento...")
        self._pool.shutdown(wait=True)