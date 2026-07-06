#!/usr/bin/env python3
"""
WoFF BHaH II Watchdog v1.5
══════════════════════════════════════════════════════════════════
Monitoriza os ficheiros de campanha do Wings over Flanders Fields:
Between Heaven and Hell II e exporta dados de missões e pilotos
em JSON compatível com a aplicação WoFFBase.

Melhorias v1.5 (Arquitetura Modular Final):
- Code cleanup total. O ficheiro principal foca-se apenas em:
  - Inicialização do Logging e CLI (Argparse)
  - Orquestração do Watchdog (Arranque/Encerramento gracioso)
  - Modo de Teste (--test)
- Toda a lógica distribuída por módulos especializados.
- Path dinâmico adicionado para resolver imports em qualquer terminal.

Modos de uso:
  Normal:     python woff/woff_watchdog.py
  Descoberta: python woff/woff_watchdog.py --discover
  Teste:      python woff/woff_watchdog.py --test
  Ajuda:      python woff/woff_watchdog.py --help
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import os
import sys
import argparse
import logging
import threading
from typing import Optional, List

# ──────────────────────────────────────────────────────────────
# CONFIGURAÇÃO DE CAMINHO (Garante que os módulos são encontrados)
# ──────────────────────────────────────────────────────────────
# Isto diz ao Python para procurar os ficheiros na mesma pasta onde este script está!
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# ──────────────────────────────────────────────────────────────
# VERIFICAÇÃO DE DEPENDÊNCIAS E MÓDULOS
# ──────────────────────────────────────────────────────────────
try:
    from watchdog.observers import Observer
except Exception as e:
    print(f"\n[ERRO DETECTADO] {type(e).__name__}: {e}\n")
    sys.exit(1)

try:
    # Imports diretos (graças ao sys.path.insert acima)
    from woff.config import WatchdogConfig, load_config
    from woff.handler import WoFFEventHandler, WoFFXMLParser
    from woff.exporter import JSONExporter
    from woff.discovery import DiscoveryLogger
except Exception as e:
    print(
        f"\n[ERRO] Módulo externo não encontrado: {type(e).__name__} - {e}\n"
        "Certifica-te que tens todos os ficheiros do projeto na mesma pasta:\n"
        " - config.py\n - models.py\n - maps.py\n - normalization.py\n"
        " - handler.py\n - exporter.py\n - discovery.py\n"
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

    def __init__(self, config: WatchdogConfig, discovery: bool = False, pilot_id: str = ""):
        self.config    = config
        self.exporter  = JSONExporter(config.export_path, config.backup_export, config.export_schema_version)
        self.discovery = DiscoveryLogger(config.discovery_log_path) if discovery else None
        self.pilot_id  = pilot_id
        self.observers: List[Observer] = []
        self._handler: Optional[WoFFEventHandler] = None
        self._stop_event = threading.Event()

    def start(self) -> bool:
        """Inicia a monitorização das pastas configuradas."""
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
                "Edita config.json com os caminhos correctos da tua instalação WoFF.\n"
            )
            return False

        # Inicializa o handler de eventos com as dependências injetadas
        self._handler = WoFFEventHandler(
            self.config, self.exporter, self.discovery, self.pilot_id
        )

        # Cria um Observer por cada caminho válido
        for path in valid:
            obs = Observer()
            obs.schedule(self._handler, path, recursive=True)
            obs.start()
            self.observers.append(obs)

        log.info(f"\nWatchdog activo — {len(valid)} caminho(s) em monitorização")
        log.info(f"Export: {self.config.export_path}")
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
# MODO TESTE — XML simulado
# ──────────────────────────────────────────────────────────────

MOCK_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Campaign>
  <Pilot>
    <PilotName>James Percival Hartley</PilotName>
    <Nation>RFC</Nation>
    <Rank>Captain</Rank>
    <Squadron>No. 56 Squadron RFC</Squadron>
    <Aircraft>SE.5a</Aircraft>
    <Aerodrome>Filescamp Farm</Aerodrome>
    <Sector>Arras</Sector>
    <StartDate>1917-04-01</StartDate>
    <Status>Active</Status>
    <Notes>Transferred from No. 60 Sqn after Bloody April.</Notes>
  </Pilot>
  <Missions>
    <Mission>
      <Date>1917-04-06</Date>
      <Type>Offensive Patrol</Type>
      <Aircraft>SE.5a</Aircraft>
      <Duration>1.5</Duration>
      <Altitude>12000</Altitude>
      <Sector>Arras</Sector>
      <Weather>Clear</Weather>
      <EnemyContacts>4</EnemyContacts>
      <Claims>1</Claims>
      <Result>Major Engagement</Result>
      <Damage>0</Damage>
      <Wounds>0</Wounds>
      <Notes>Intercepted Jasta 11 formation east of Arras.</Notes>
    </Mission>
  </Missions>
  <Victories>
    <Victory>
      <Date>1917-04-06</Date>
      <Time>10:35</Time>
      <EnemyType>Albatros D.III</EnemyType>
      <Type>Out of Control</Type>
      <Confirmed>true</Confirmed>
      <Witnesses>Lt. Richardson, 56 Sqn</Witnesses>
    </Victory>
  </Victories>
  <Decorations>
    <Decoration>
      <Name>Military Cross (MC)</Name>
      <Date>1917-04-15</Date>
      <Citation>For conspicuous gallantry.</Citation>
    </Decoration>
  </Decorations>
</Campaign>
"""


def run_test(config: WatchdogConfig):
    """Executa um teste rápido do parser e do exportador usando dados fictícios."""
    import tempfile
    sep = "═" * 50
    log.info(f"\n{sep}")
    log.info("MODO TESTE — XML simulado do WoFF")
    log.info(sep)

    # Cria ficheiro temporário com o XML de teste
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".xml", delete=False, encoding="utf-8"
    ) as f:
        f.write(MOCK_XML)
        tmp = f.name

    try:
        # Utiliza o Parser importado do handler.py
        parser = WoFFXMLParser()
        ok     = parser.parse(tmp)

        if ok and parser.pilot:
            p = parser.pilot
            log.info(f"\nPiloto:")
            log.info(f"  Nome:     {p.name}")
            log.info(f"  Nação:    {p.nation}")
            log.info(f"  Posto:    {p.rank}")
            log.info(f"  Estado:   {p.status}")
            log.info(f"\nMissões ({len(parser.missions)}):")
            for m in parser.missions:
                log.info(f"  [{m.date}] {m.missionType} — {m.result}")
            log.info(f"\nVitórias ({len(parser.victories)}):")
            for v in parser.victories:
                log.info(f"  [{v.date}] {v.enemyType} — {v.victoryType} | Confirmado: {v.confirmed}")

            # Testa a escrita do Exportador
            test_path = os.path.join(
                os.path.dirname(os.path.abspath(config.export_path)),
                "woff_test_export.json"
            )
            exp = JSONExporter(test_path, backup=False)
            exp.merge_and_write(
                parser.pilot, parser.missions,
                parser.victories, parser.decorations
            )
            log.info(f"\n✓ Export de teste escrito em: {test_path}")
            log.info(f"\n{sep}")
            log.info("Teste concluído com sucesso!")
        else:
            log.error("✗ Parser não encontrou dados — verifica o XML")
    finally:
        os.unlink(tmp)


# ──────────────────────────────────────────────────────────────
# PONTO DE ENTRADA
# ──────────────────────────────────────────────────────────────

BANNER = r"""
╔══════════════════════════════════════════════════════════╗
║      ✈  WoFF BHaH II — Watchdog  v1.5  ✈              ║
║   Wings over Flanders Fields · Companion Sync Tool      ║
╚══════════════════════════════════════════════════════════╝
"""


def main():
    """Ponto de entrada da aplicação."""
    ap = argparse.ArgumentParser(
        description="WoFF BHaH II Watchdog — sincroniza campanha com WoFFBase",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Exemplos:
  python woff/woff_watchdog.py                    Monitorização normal
  python woff/woff_watchdog.py --discover         Regista todos os ficheiros detectados
  python woff/woff_watchdog.py --test             Testa o parser com dados simulados
  python woff/woff_watchdog.py --config meu.json  Usa ficheiro de config alternativo
  python woff/woff_watchdog.py --verbose          Log detalhado (DEBUG)
"""
    )
    ap.add_argument("--config",   default="config.json",
                    help="Caminho para config.json (padrão: config.json)")
    ap.add_argument("--discover", action="store_true",
                    help="Modo descoberta: regista todos os ficheiros detectados")
    ap.add_argument("--test",     action="store_true",
                    help="Modo teste: corre parser com XML simulado")
    ap.add_argument("--pilot",    default="",
                    help="ID do piloto para associar a ficheiros de texto")
    ap.add_argument("--verbose",  action="store_true",
                    help="Log detalhado (DEBUG)")
    args = ap.parse_args()

    print(BANNER)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Carrega configuração do config.py
    cfg = load_config(args.config)
    if args.verbose or cfg.log_level == "DEBUG":
        logging.getLogger().setLevel(logging.DEBUG)

    # Se for modo teste, corre a função e sai
    if args.test:
        run_test(cfg)
        return

    # Inicializa o orquestrador
    dog = WoFFWatchdog(cfg, discovery=args.discover, pilot_id=args.pilot)
    if dog.start():
        dog.run_forever()


if __name__ == "__main__":
    main()