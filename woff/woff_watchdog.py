#!/usr/bin/env python3
"""
WoFF BHaH II Watchdog v2.2
══════════════════════════════════════════════════════════════════
Monitoriza os ficheiros de campanha do Wings over Flanders Fields:
Between Heaven and Hell II e exporta dados de missões e pilotos
em SQLite compatível com a aplicação WoFFBase.

Melhorias v2.2:
- Injeção de Dependências: CampaignEngine instanciado uma única vez.
- Sincronização inicial suporta múltiplos pilotos (Pilot1, Pilot2, etc.).
- Procura dinâmica das pastas Medals e Scratchpad em todos os caminhos.
- Correção do roteamento de ficheiros .log no modo --parse-file.
- Debounce de eventos para evitar processamento duplicado.
- Null-safety rigorosa para aprovação em analisadores estáticos (Pyright).

Modos de uso:
  Normal:       python woff/woff_watchdog.py
  Debug:        python woff/woff_watchdog.py --parse-file "caminho/para/ficheiro.txt"
  Descoberta:   python woff/woff_watchdog.py --discover
  Ajuda:        python woff/woff_watchdog.py --help
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import os
import sys
import glob
import argparse
import logging
import threading
from typing import Optional, List, Any

# ──────────────────────────────────────────────────────────────
# CONFIGURAÇÃO DE CAMINHO (Garante que os módulos são encontrados)
# ──────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# ──────────────────────────────────────────────────────────────
# VERIFICAÇÃO DE DEPENDÊNCIAS E MÓDULOS
# ──────────────────────────────────────────────────────────────
try:
    from watchdog.observers import Observer
except Exception as e:
    print(f"\n[ERRO] Falha ao importar a biblioteca 'watchdog': {type(e).__name__} - {e}\n")
    sys.exit(1)

try:
    from config import WatchdogConfig, load_config
    from handler import WoFFEventHandler
    from database import DatabaseManager
    from discovery import DiscoveryLogger
    from medal_cataloger import catalog_medals
    from squadron_cataloger import catalog_squadrons
    from campaign_engine import CampaignEngine
    
    # Importar os Parsers para a ferramenta de debug e leitura inicial
    from parsers.xml_parser import WoFFXMLParser
    from parsers.mission_log_parser import WoFFMissionLogParser
    from parsers.pilot_data_parser import WoFFPilotDataParser
    from parsers.dossier_parser import WoFFDossierParser
except Exception as e:
    print(f"\n[ERRO MODULOS] {type(e).__name__}: {e}\n")
    sys.exit(1)

# ──────────────────────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────────────────────
LOG_FORMAT = "[%(asctime)s] %(levelname)-8s  %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt="%H:%M:%S")
log = logging.getLogger("WoFFWatch")


# ──────────────────────────────────────────────────────────────
# ORQUESTRADOR PRINCIPAL
# ──────────────────────────────────────────────────────────────

class WoFFWatchdog:
    """
    Classe principal que gere o ciclo de vida do watchdog.
    """

    def __init__(self, config: WatchdogConfig, discovery: bool = False, pilot_id: str = ""):
        self.config    = config
        self.db_manager = DatabaseManager(config.export_path, config.export_schema_version)
        self.discovery = DiscoveryLogger(config.discovery_log_path) if discovery else None
        self.pilot_id  = pilot_id
        # FIX: Usar Any para evitar conflitos de tipagem do Pyright com watchdog.Observer
        self.observers: List[Any] = []
        self._handler: Optional[WoFFEventHandler] = None
        self._stop_event = threading.Event()

    def start(self) -> bool:
        """Inicia a monitorização das pastas configuradas e cataloga dados estáticos do jogo."""
        paths = self.config.watch_paths
        valid = [p for p in paths if os.path.exists(p)]
        missing = [p for p in paths if not os.path.exists(p)]

        for p in valid:
            log.info(f"  ✓ Monitorizar: {p}")
        for p in missing:
            log.warning(f"  ✗ Não encontrado: {p}")

        if not valid:
            log.error("\nNenhum caminho válido encontrado!\nEdita o config.json com os caminhos correctos.\n")
            return False

        # Procurar as pastas 'Medals' e 'Scratchpad' em todos os caminhos válidos
        medals_path = None
        scratchpad_path = None
        for path in valid:
            if not medals_path and os.path.exists(os.path.join(path, "Medals")):
                medals_path = os.path.join(path, "Medals")
            if not medals_path and os.path.exists(os.path.join(os.path.dirname(path), "Medals")):
                medals_path = os.path.join(os.path.dirname(path), "Medals")
                
            if not scratchpad_path and os.path.exists(os.path.join(path, "Scratchpad")):
                scratchpad_path = os.path.join(path, "Scratchpad")
            if not scratchpad_path and os.path.exists(os.path.join(os.path.dirname(path), "Scratchpad")):
                scratchpad_path = os.path.join(os.path.dirname(path), "Scratchpad")

        if medals_path:
            catalog_medals(medals_path, self.config.export_path)
        if scratchpad_path:
            catalog_squadrons(scratchpad_path, self.config.export_path)

        # ──────────────────────────────────────────────────────────────
        # SINCRONIZAÇÃO INICIAL DE TODOS OS PILOTOS
        # ──────────────────────────────────────────────────────────────
        log.info("A sincronizar dados iniciais dos pilotos...")
        
        # Instanciar o CampaignEngine uma única vez para partilhar entre o arranque e o runtime
        self.campaign_engine = CampaignEngine(self.db_manager)
        
        for path in valid:
            for file_pattern in ["Pilot*Dossier.txt", "Pilot*Log.txt", "Pilot*Claims.txt", "Pilot*Squads.txt"]:
                for file_path in glob.glob(os.path.join(path, file_pattern)):
                    fname = os.path.basename(file_path).lower()
                    
                    try:
                        if "dossier" in fname:
                            parser = WoFFDossierParser()
                            if parser.parse(file_path):
                                # FIX: Null-safety check para parser.pilot
                                if not parser.pilot: continue
                                    
                                old_status, old_rank = self.db_manager.get_pilot_state(parser.pilot.name)
                                self.db_manager.merge_and_write(
                                    pilot=parser.pilot, missions=[], victories=[],
                                    decorations=parser.decorations, wingmen=parser.wingmen
                                )
                                new_status = parser.pilot.status
                                new_rank = parser.pilot.rank
                                
                                # FIX: Tratar os retornos Optional[str] do get_pilot_state
                                old_status_str = old_status if old_status is not None else ""
                                old_rank_str = old_rank if old_rank is not None else ""
                                
                                if (old_status_str != new_status) or (old_rank_str != new_rank and new_rank):
                                    self.campaign_engine.process_life_events(
                                        parser.pilot.name, new_status, new_rank, old_status_str, old_rank_str
                                    )
                        elif "squads" in fname:
                            parser = WoFFPilotDataParser()
                            if parser.parse(file_path):
                                self.db_manager.merge_and_write(
                                    pilot=parser.pilot, missions=[], victories=[], decorations=[]
                                )
                        elif "log" in fname and "mission" not in fname:
                            parser = WoFFPilotDataParser()
                            if parser.parse(file_path):
                                self.db_manager.merge_and_write(
                                    pilot=parser.pilot, missions=parser.missions, 
                                    victories=[], decorations=[]
                                )
                                # FIX: Null-safety check para parser.pilot
                                if parser.missions and parser.pilot and parser.pilot.name:
                                    self.campaign_engine.process_mission_end(
                                        parser.pilot.name, parser.missions[0].id
                                    )
                        elif "claims" in fname:
                            parser = WoFFPilotDataParser()
                            if parser.parse(file_path):
                                self.db_manager.merge_and_write(
                                    pilot=None, missions=[], 
                                    victories=parser.victories, decorations=[]
                                )
                    except Exception as e:
                        log.error(f"Erro ao sincronizar inicialmente {file_path}: {e}")

        # Injetar a mesma instância do CampaignEngine no Handler
        self._handler = WoFFEventHandler(
            self.config, self.db_manager, self.campaign_engine, self.discovery, self.pilot_id
        )

        for path in valid:
            obs = Observer()
            obs.schedule(self._handler, path, recursive=True)
            obs.start()
            self.observers.append(obs)

        log.info(f"\nWatchdog activo — {len(valid)} caminho(s) em monitorização")
        log.info(f"Base de Dados: {self.config.export_path}")
        if self.discovery:
            log.info(f"Discovery log: {self.config.discovery_log_path}")
        log.info("Pressiona Ctrl+C para parar.\n")
        return True

    def run_forever(self):
        """Mantém o programa a correr até ser interrompido (Ctrl+C)."""
        try:
            while not self._stop_event.is_set():
                self._stop_event.wait(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        """Encerra todos os observers e threads de forma graciosa."""
        log.info("A parar watchdog...")
        self._stop_event.set()
        for obs in self.observers:
            obs.stop()
        for obs in self.observers:
            obs.join(timeout=5)
        if self._handler:
            self._handler.shutdown()
        log.info("Watchdog parado.")


# ──────────────────────────────────────────────────────────────
# MODO DEBUG --parse-file
# ──────────────────────────────────────────────────────────────

def run_parse_file(file_path: str):
    """Lê um único ficheiro e imprime os dados extraídos no terminal."""
    sep = "═" * 60
    log.info(f"\n{sep}")
    log.info(f"🎯 MODO DEBUG --parse-file: {file_path}")
    log.info(sep)

    if not os.path.exists(file_path):
        log.error(f"Ficheiro não encontrado: {file_path}")
        return

    ext = os.path.splitext(file_path)[1].lower()
    fname = os.path.basename(file_path).lower()
    
    if ext == ".xml":
        parser = WoFFXMLParser()
        if parser.parse(file_path):
            log.info(f"Piloto: {parser.pilot.name if parser.pilot else 'N/A'}")
            log.info(f"Missões: {len(parser.missions)} | Vitórias: {len(parser.victories)}")
        else:
            log.warning("Parser não encontrou dados válidos.")
            
    elif ext in (".txt", ".log"):
        # 1. Se for o ficheiro Dossier (Binário Ofuscado)
        if "dossier" in fname:
            log.info("\n--- 🗄️ A DESOFUSCAR DOSSIER BINÁRIO ---")
            parser = WoFFDossierParser()
            if parser.parse(file_path):
                if parser.pilot:
                    log.info("\n--- 🧑‍✈️ DADOS DO PILOTO ---")
                    log.info(f"Nome: {parser.pilot.name}")
                    log.info(f"Patente: {parser.pilot.rank} | Nação: {parser.pilot.nation}")
                    log.info(f"Esquadrão: {parser.pilot.squadron} | Base: {parser.pilot.aerodrome}")
                    log.info(f"Status: {parser.pilot.status} | Skill: {parser.pilot.skill}")
                    log.info(f"Missões: {parser.pilot.missions} | Minutos Voo: {parser.pilot.flminutes}")
                    log.info(f"Vitórias: {parser.pilot.killsCount} | Reputação: {parser.pilot.reputation}")
                    log.info(f"Data Nasc.: {parser.pilot.birthDate} ({parser.pilot.birthPlace})")
                    log.info(f"Foto ID: {parser.pilot.photo}")
                    log.info(f"Biografia: {parser.pilot.notes[:150]}...")
                    
                if parser.decorations:
                    log.info("\n--- 🎖️ MEDALHAS RECEBIDAS ---")
                    for d in parser.decorations:
                        log.info(f"  -> {d.name} ({d.date})")
                        
                if parser.wingmen:
                    log.info("\n--- 👥 MEMBROS DO ESQUADRÃO (AI) ---")
                    for w in parser.wingmen:
                        log.info(f"  -> {w.rank} {w.fName} {w.sName} (Skill: {w.skill}, Status: {w.status})")
                        if w.bio:
                            log.info(f"     Bio: {w.bio[:80]}...")
            else:
                log.warning("Parser não encontrou dados válidos.")
            return
            
        # 2. Se for EXATAMENTE o mission.log do motor do jogo
        elif fname == "mission.log":
            parser = WoFFMissionLogParser()
            if parser.parse(file_path):
                log.info("\n--- 📜 BRIEFING DA MISSÃO ---")
                log.info(parser.briefing[:300] + "..." if len(parser.briefing) > 300 else parser.briefing)
                
                log.info("\n--- 🛩️ DADOS DA MISSÃO ---")
                m = parser.mission
                if m:
                    log.info(f"Data: {m.date} | Tempo: {m.weather}")
                    log.info(f"Aeronave do Jogador: {m.aircraft}")
                    # FIX: Null-safety check para parser.pilot
                    if parser.pilot:
                        log.info(f"Esquadrão: {parser.pilot.squadron} ({parser.pilot.nation})")
                    
                log.info("\n--- 👥 MEMBROS DO ESQUADRÃO (Flight) ---")
                for member in parser.squad_members:
                    log.info(member)
                    
                log.info("\n--- 🗺️ PLANO DE VOO ---")
                for wp in parser.flight_plan:
                    log.info(f"  -> {wp['type']} | Alt: {wp['altitude']}m | Lat: {wp['lat']} | Lon: {wp['lon']}")
                    
                log.info("\n--- 📝 DEBRIEFING ---")
                log.info(parser.debriefing if parser.debriefing else "Sem debriefing textual encontrado.")
            else:
                log.warning("Parser não encontrou dados válidos.")
            return
            
        # 3. Restantes ficheiros de piloto (Log.txt, Claims.txt, Squads.txt)
        else:
            parser = WoFFPilotDataParser()
            if parser.parse(file_path):
                if parser.pilot:
                    log.info("\n--- 🧑‍✈️ DADOS DO PILOTO ---")
                    log.info(f"Nome (ID): {parser.pilot.name}")
                    log.info(f"Esquadrão: {parser.pilot.squadron}")
                    log.info(f"Aeronave Atual: {parser.pilot.aircraft}")
                    log.info(f"Base: {parser.pilot.aerodrome}")
                    log.info(f"Patente: {parser.pilot.rank}")
                    
                log.info(f"\nMissões extraídas do log: {len(parser.missions)}")
                for m in parser.missions[:3]:
                    log.info(f"  -> [{m.date}] {m.missionType} ({m.aircraft})")
                    
                log.info(f"\nVitórias extraídas: {len(parser.victories)}")
                for v in parser.victories[:3]:
                    log.info(f"  -> [{v.date}] {v.enemyType} ({v.victoryType})")
            else:
                log.warning("Parser não encontrou dados válidos ou ficheiro não suportado.")
    else:
        log.error(f"Extensão não suportada para parse: {ext}")


# ──────────────────────────────────────────────────────────────
# PONTO DE ENTRADA
# ──────────────────────────────────────────────────────────────

BANNER = r"""
╔══════════════════════════════════════════════════════════╗
║      ✈  WoFF BHaH II — Watchdog  v2.2  ✈              ║
║   Wings over Flanders Fields · SQLite Companion Sync    ║
╚══════════════════════════════════════════════════════════╝
"""


def main():
    """Ponto de entrada da aplicação."""
    ap = argparse.ArgumentParser(
        description="WoFF BHaH II Watchdog — sincroniza campanha com WoFFBase",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Exemplos:
  python woff/woff_watchdog.py                            Monitorização normal
  python woff/woff_watchdog.py --parse-file "A:\\...\\Pilot1Dossier.txt"  Testa um ficheiro
  python woff/woff_watchdog.py --discover                 Regista todos os ficheiros detectados
  python woff/woff_watchdog.py --verbose                  Log detalhado (DEBUG)
"""
    )
    ap.add_argument("--config",   default="config.json",
                    help="Caminho para config.json (padrão: config.json)")
    ap.add_argument("--discover", action="store_true",
                    help="Modo descoberta: regista todos os ficheiros detectados")
    ap.add_argument("--parse-file", default="",
                    help="Testa a extração de um ficheiro específico sem iniciar o watchdog")
    ap.add_argument("--verbose",  action="store_true",
                    help="Log detalhado (DEBUG)")
    args = ap.parse_args()

    print(BANNER)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    cfg = load_config(args.config)
    if args.verbose or cfg.log_level == "DEBUG":
        logging.getLogger().setLevel(logging.DEBUG)

    # Modo Debug de ficheiro único
    if args.parse_file:
        run_parse_file(args.parse_file)
        return

    # Inicializa o orquestrador
    dog = WoFFWatchdog(cfg, discovery=args.discover, pilot_id="")
    if dog.start():
        dog.run_forever()


if __name__ == "__main__":
    main()