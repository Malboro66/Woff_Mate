#!/usr/bin/env python3
"""
Módulo de Descoberta (discovery.py)
══════════════════════════════════════════════════════════════════
Responsável por registar todos os ficheiros detetados pelo watchdog
e o seu conteúdo em bruto.

Usado no modo --discover para ajudar a conhecer a estrutura real dos 
ficheiros gerados pelo WoFF antes de refinar os parsers.

Procedimento de utilização:
  1. Executar: python woff_watchdog.py --discover
  2. Jogar uma missão completa no WoFF
  3. Analisar o ficheiro 'woff_discovery.log' para ver os ficheiros gerados
  4. Atualizar os parsers com base no que for encontrado
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger("WoFFWatch")


class DiscoveryLogger:
    """
    Regista todos os ficheiros detectados e o seu conteúdo num ficheiro de log.
    """
    PREVIEW_LIMIT = 12_000  # bytes máximos a registar por ficheiro

    def __init__(self, log_path: str):
        self.log_path = Path(log_path)
        
        # Escreve o cabeçalho da sessão de descoberta
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'═'*60}\n")
            f.write(f"SESSÃO DE DESCOBERTA — {datetime.now().isoformat()}\n")
            f.write(f"{'═'*60}\n")
            
        log.info(f"Modo descoberta ativo — log: {self.log_path}")

    def log_file(self, path: str, event_type: str):
        """
        Regista um evento de ficheiro no log de descoberta.
        Tenta fazer um preview do conteúdo se for um ficheiro de texto pequeno.
        """
        try:
            p = Path(path)
            size = p.stat().st_size if p.exists() else 0
            ext  = p.suffix.lower()
            
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now().isoformat()}] Evento: {event_type.upper()}\n")
                f.write(f"Ficheiro: {path}\n")
                f.write(f"Tamanho: {size} bytes | Extensão: {ext}\n")
                
                # Verifica se deve fazer preview do conteúdo
                if size > 0 and size < 1_000_000 and ext in (".xml", ".txt", ".log", ".ini", ".cfg", ".csv"):
                    try:
                        with open(p, "r", encoding="utf-8", errors="replace") as src:
                            content = src.read(self.PREVIEW_LIMIT)
                        f.write(f"{'─'*40} Conteúdo ({min(size, self.PREVIEW_LIMIT)}/{size}B) {'─'*10}\n")
                        f.write(content)
                        f.write(f"\n{'─'*60}\n")
                    except Exception as e:
                        f.write(f"Erro ao ler conteúdo: {e}\n")
                elif size >= 1_000_000:
                    f.write(f"[Ficheiro muito grande — sem preview]\n")
                else:
                    f.write(f"[Binário ou extensão desconhecida — sem preview]\n")
                    
            log.info(f"[DISCOVER] {event_type}: {p.name} ({size}B)")
            
        except Exception as e:
            log.error(f"Erro no discovery log: {e}")