#!/usr/bin/env python3
"""
WoFF BHaH II Watchdog v3.2
══════════════════════════════════════════════════════════════════
Monitoriza os ficheiros de campanha do Wings over Flanders Fields:
Between Heaven and Hell II e exporta dados de missões e pilotos
em SQLite compatível com a aplicação WoFFBase.

Melhorias v3.2 (Correção de Integração):
- RPG e Diário de Missão agora usam o pilot_id real (resolve "Pilot 1").
- Eventos de Vida e Wingmen usam a data do jogo (imersão histórica).
- Wingmen: aborta comparação se lista vazia (evita spam "missing").
- Dossier: normaliza nação e datas de nascimento.
- Sincronização inicial usa resolve_pilot_id com source_file para garantir
  resolução correta de placeholders "Pilot X" → UUID real.

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
from datetime import datetime

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
except ImportError:
    print(
        "\n[ERRO] Falha ao carregar a biblioteca 'watchdog'.\n"
        "Para corrigir, executa no terminal:\n"
        "  pip install watchdog\n"
    )
    sys.exit(1)
except Exception as e:
    print(
        f"\n[ERRO] Ocorreu um erro inesperado: {type(e).__name__} - {e}\n"
        "Verifica a tua instalação do Python e do pacote 'watchdog'."
    )
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
except ImportError as e:
    print(
        f"\n[ERRO] Falha ao carregar módulos internos: {type(e).__name__} - {e}\n"
        "Certifica-te que todos os ficheiros do projeto estão na pasta correta.\n"
        "Se o problema persistir, reinstala as dependências:\n"
        "  pip install watchdog pywin32\n"
    )
    sys.exit(1)
except Exception as e:
    print(
        f"\n[ERRO] Ocorreu um erro ao carregar os módulos: {type(e).__name__} - {e}"
    )
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

    def __init__(
        self, config: WatchdogConfig, discovery: bool = False, pilot_id: str = ""
    ):
        self.config = config
        self.db_manager = DatabaseManager(
            config.export_path, config.export_schema_version
        )
        self.discovery = (
            DiscoveryLogger(config.discovery_log_path) if discovery else None
        )
        self.pilot_id = pilot_id
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
            log.error(
                "\nNenhum caminho válido encontrado!\n"
                "Edita o config.json com os caminhos correctos.\n"
            )
            return False

        # Procurar as pastas 'Medals' e 'Scratchpad' em todos os caminhos válidos
        medals_path = None
        scratchpad_path = None
        for path in valid:
            if not medals_path and os.path.exists(os.path.join(path, "Medals")):
                medals_path = os.path.join(path, "Medals")
            if not medals_path and os.path.exists(
                os.path.join(os.path.dirname(path), "Medals")
            ):
                medals_path = os.path.join(os.path.dirname(path), "Medals")

            if not scratchpad_path and os.path.exists(
                os.path.join(path, "Scratchpad")
            ):
                scratchpad_path = os.path.join(path, "Scratchpad")
            if not scratchpad_path and os.path.exists(
                os.path.join(os.path.dirname(path), "Scratchpad")
            ):
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
            for file_pattern in [
                "Pilot*Dossier.txt",
                "Pilot*Log.txt",
                "Pilot*Claims.txt",
                "Pilot*Squads.txt",
            ]:
                for file_path in glob.glob(os.path.join(path, file_pattern)):
                    fname = os.path.basename(file_path).lower()

                    # FIX: Extrair data do ficheiro para eventos históricos
                    try:
                        file_mtime = datetime.fromtimestamp(
                            os.path.getmtime(file_path)
                        ).strftime("%Y-%m-%d")
                    except OSError:
                        file_mtime = None

                    try:
                        if "dossier" in fname:
                            parser = WoFFDossierParser()
                            if parser.parse(file_path):
                                if not parser.pilot:
                                    continue

                                old_status, old_rank = self.db_manager.get_pilot_state(
                                    parser.pilot.name
                                )

                                # FIX: Passar data do ficheiro para não gerar entradas em 2026
                                self.campaign_engine.process_wingmen_changes(
                                    parser.pilot.name,
                                    parser.wingmen,
                                    event_date=file_mtime,
                                )

                                self.db_manager.merge_and_write(
                                    pilot=parser.pilot,
                                    missions=[],
                                    victories=[],
                                    decorations=parser.decorations,
                                    wingmen=parser.wingmen,
                                )

                                new_status = parser.pilot.status
                                new_rank = parser.pilot.rank
                                old_status_str = old_status if old_status is not None else ""
                                old_rank_str = old_rank if old_rank is not None else ""

                                if (old_status_str != new_status) or (
                                    old_rank_str != new_rank and new_rank
                                ):
                                    self.campaign_engine.process_life_events(
                                        parser.pilot.name,
                                        str(new_status),
                                        str(new_rank),
                                        old_status,
                                        old_rank,
                                        event_date=file_mtime,
                                    )

                        elif "squads" in fname:
                            parser = WoFFPilotDataParser()
                            if parser.parse(file_path):
                                self.db_manager.merge_and_write(
                                    pilot=parser.pilot,
                                    missions=[],
                                    victories=[],
                                    decorations=[],
                                    wingmen=None,
                                )

                        elif "log" in fname and "mission" not in fname:
                            parser = WoFFPilotDataParser()
                            if parser.parse(file_path):
                                self.db_manager.merge_and_write(
                                    pilot=parser.pilot,
                                    missions=parser.missions,
                                    victories=[],
                                    decorations=[],
                                    wingmen=None,
                                )
                                if (
                                    parser.missions
                                    and parser.pilot
                                    and parser.pilot.name
                                ):
                                    # FIX: Usar resolve_pilot_id com source_file para
                                    # resolver "Pilot 1" (placeholder) → UUID real.
                                    real_pilot_id = self.db_manager.resolve_pilot_id(
                                        parser.pilot.name,
                                        source_file=parser.pilot.source_file,
                                    )
                                    if real_pilot_id:
                                        self.campaign_engine.process_mission_end(
                                            real_pilot_id, parser.missions[0].id
                                        )
                                    else:
                                        log.warning(
                                            f"[Sync] Não foi possível resolver "
                                            f"pilot_id real para '{parser.pilot.name}' "
                                            f"(source: {parser.pilot.source_file}). "
                                            f"RPG abortado na sincronização inicial."
                                        )

                        elif "claims" in fname:
                            parser = WoFFPilotDataParser()
                            if parser.parse(file_path):
                                self.db_manager.merge_and_write(
                                    pilot=None,
                                    missions=[],
                                    victories=parser.victories,
                                    decorations=[],
                                    wingmen=None,
                                )
                    except Exception:
                        log.exception(
                            f"Erro ao sincronizar inicialmente {file_path}"
                        )

        # Injetar a mesma instância do CampaignEngine no Handler
        self._handler = WoFFEventHandler(
            self.config, self.db_manager, self.campaign_engine, self.discovery
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
        # FIX: Libertar conexões thread-local do DatabaseManager
        self.db_manager.close()
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
            log.info(
                f"Piloto: {parser.pilot.name if parser.pilot else 'N/A'}"
            )
            log.info(
                f"Missões: {len(parser.missions)} | "
                f"Vitórias: {len(parser.victories)}"
            )
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
                    log.info(
                        f"Patente: {parser.pilot.rank} | "
                        f"Nação: {parser.pilot.nation}"
                    )
                    log.info(
                        f"Esquadrão: {parser.pilot.squadron} | "
                        f"Base: {parser.pilot.aerodrome}"
                    )
                    log.info(
                        f"Status: {parser.pilot.status} | "
                        f"Skill: {parser.pilot.skill}"
                    )
                    log.info(
                        f"Missões: {parser.pilot.missions} | "
                        f"Minutos Voo: {parser.pilot.flminutes}"
                    )
                    log.info(
                        f"Vitórias: {parser.pilot.killsCount} | "
                        f"Reputação: {parser.pilot.reputation}"
                    )
                    log.info(
                        f"Data Nasc.: {parser.pilot.birthDate} "
                        f"({parser.pilot.birthPlace})"
                    )
                    log.info(f"Foto ID: {parser.pilot.photo}")
                    log.info(f"Biografia: {parser.pilot.notes[:150]}...")

                if parser.decorations:
                    log.info("\n--- 🎖️ MEDALHAS RECEBIDAS ---")
                    for d in parser.decorations:
                        log.info(f"  -> {d.name} ({d.date})")

                if parser.wingmen:
                    log.info("\n--- 👥 MEMBROS DO ESQUADRÃO (AI) ---")
                    for w in parser.wingmen:
                        log.info(
                            f"  -> {w.rank} {w.fName} {w.sName} "
                            f"(Skill: {w.skill}, Status: {w.status})"
                        )
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
                if len(parser.briefing) > 300:
                    log.info(parser.briefing[:300] + "...")
                else:
                    log.info(parser.briefing)

                log.info("\n--- 🛩️ DADOS DA MISSÃO ---")
                m = parser.mission
                if m:
                    log.info(f"Data: {m.date} | Tempo: {m.weather}")
                    log.info(f"Aeronave do Jogador: {m.aircraft}")
                    if parser.pilot:
                        log.info(
                            f"Esquadrão: {parser.pilot.squadron} "
                            f"({parser.pilot.nation})"

                        )

                log.info("\n--- 👥 MEMBROS DO ESQUADRÃO (Flight) ---")
                for member in parser.squad_members:
                    log.info(member)

                log.info("\n--- 🗺️ PLANO DE VOO ---")
                for wp in parser.flight_plan:
                    log.info(
                        f"  -> {wp['type']} | Alt: {wp['altitude']}m | "
                        f"Lat: {wp['lat']} | Lon: {wp['lon']}"
                    )

                log.info("\n--- 📝 DEBRIEFING ---")
                log.info(
                    parser.debriefing
                    if parser.debriefing
                    else "Sem debriefing textual encontrado."
                )
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
                    log.info(
                        f"  -> [{m.date}] {m.missionType} ({m.aircraft})"
                    )

                log.info(f"\nVitórias extraídas: {len(parser.victories)}")
                for v in parser.victories[:3]:
                    log.info(
                        f"  -> [{v.date}] {v.enemyType} ({v.victoryType})"
                    )
            else:
                log.warning(
                    "Parser não encontrou dados válidos ou ficheiro não suportado."
                )
    else:
        log.error(f"Extensão não suportada para parse: {ext}")


# ──────────────────────────────────────────────────────────────
# PONTO DE ENTRADA
# ──────────────────────────────────────────────────────────────

BANNER = r"""
╔════════════════════════════════════════════════════════════╗
║      ✈  WoFF BHaH II — Watchdog  v3.2  ✈                 ║
║   Wings over Flanders Fields · SQLite Companion Sync       ║
╚════════════════════════════════════════════════════════════╝
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
""",
    )
    ap.add_argument(
        "--config",
        default="config.json",
        help="Caminho para config.json (padrão: config.json)",
    )
    ap.add_argument(
        "--discover",
        action="store_true",
        help="Modo descoberta: regista todos os ficheiros detectados",
    )
    ap.add_argument(
        "--parse-file",
        default="",
        help="Testa a extração de um ficheiro específico sem iniciar o watchdog",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Log detalhado (DEBUG)",
    )
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