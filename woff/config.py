#!/usr/bin/env python3
"""
Módulo de Configuração (config.py)
══════════════════════════════════════════════════════════════════
Responsável por definir, carregar e validar a configuração do 
WoFF Watchdog.

Utiliza Dataclasses para garantir um esquema rígido e seguro, 
evitando erros de KeyErrors caso o utilizador apague acidentalmente 
campos do ficheiro config.json.

Inclui Auto-Deteção do caminho do jogo via Registo do Windows.
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List

log = logging.getLogger("WoFFWatch")


@dataclass
class WatchdogConfig:
    """Estrutura de configuração rigorosa do WoFF Watchdog."""
    watch_paths: List[str] = field(default_factory=list)
    export_path: str = "C:\\Users\\Public\\WoFFBase\\woff_data.db"
    watched_extensions: List[str] = field(default_factory=lambda: [".txt", ".xml", ".log"])
    stability_timeout_sec: float = 3.0
    stability_check_interval_sec: float = 0.15
    backup_export: bool = True
    discovery_log_path: str = "woff_discovery.log"
    log_level: str = "INFO"
    max_workers: int = 4
    export_schema_version: str = "2.2" # ATUALIZADO

    @classmethod
    def from_dict(cls, d: dict) -> "WatchdogConfig":
        """Cria a configuração a partir de um dicionário, avisando sobre chaves inválidas."""
        valid_keys = cls.__dataclass_fields__.keys()
        unknown_keys = [k for k in d.keys() if k not in valid_keys]
        
        if unknown_keys:
            log.warning(f"⚠ Chaves desconhecidas no config.json ignoradas: {unknown_keys}")
            log.warning("Verifica se há erros de digitação no ficheiro de configuração.")
            
        valid = {k: v for k, v in d.items() if k in valid_keys}
        return cls(**valid)

    def to_dict(self) -> dict:
        """Converte a configuração para dicionário (para guardar em JSON)."""
        return asdict(self)


def load_config(path: str) -> WatchdogConfig:
    """
    Carrega a configuração de um ficheiro JSON.
    Se o ficheiro não existir, tenta auto-detectar o caminho do jogo no Registo do Windows.
    Se estiver corrompido, avisa o utilizador e usa os valores padrão.
    """
    p = Path(path)
    
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = WatchdogConfig.from_dict(data)
            log.info(f"Configuração carregada: {path}")
            return cfg
        except Exception as e:
            log.warning(f"Erro ao ler config ({e}) — tentando auto-deteção.")
    else:
        log.info("config.json não encontrado. A tentar auto-deteção...")
        
    # Tenta Auto-Deteção via Registo do Windows
    try:
        from .win_registry import get_woff_install_path
        woff_path = get_woff_install_path()
        
        if woff_path:
            default_cfg = WatchdogConfig()
            base_path = Path(woff_path)
            
            # Configura os caminhos automaticamente
            pilots_path = base_path / "campaigns" / "CampaignData" / "Pilots"
            
            # Corrigido: Os Logs costumam estar uma pasta acima do caminho base do jogo
            logs_path = base_path.parent / "Logs"
            if not logs_path.exists():
                logs_path = base_path / "Logs"
            
            # Validação: Será que os caminhos realmente existem no disco?
            valid_pilots = pilots_path.exists()
            valid_logs = logs_path.exists()
            
            default_cfg.watch_paths = [str(pilots_path), str(logs_path)]
            default_cfg.export_path = str(Path.home() / "Documents" / "WoFFBase" / "woff_data.db")
            
            # Guarda o config para o utilizador poder editar no futuro
            with open(p, "w", encoding="utf-8") as f:
                json.dump(default_cfg.to_dict(), f, indent=2, ensure_ascii=False)
                
            # Feedback inteligente ao utilizador
            if valid_pilots and valid_logs:
                log.info(f"✓ Auto-deteção bem-sucedida! config.json criado em: {p}")
            else:
                log.warning("⚠ Auto-deteção encontrou o jogo no Registo, mas as pastas padrão não existem:")
                if not valid_pilots: log.warning(f"  -> Pilots não encontrado em: {pilots_path}")
                if not valid_logs: log.warning(f"  -> Logs não encontrado em: {logs_path}")
                log.warning("Por favor, edite o ficheiro config.json manualmente com os caminhos corretos.")
                
            return default_cfg
    except ImportError:
        log.warning("Módulo de registo não disponível. A usar valores padrão.")
    except Exception as e:
        log.error(f"Falha na auto-deteção: {e}")
        
    # Fallback final se a auto-deteção falhar
    log.warning("A usar valores padrão. Edita o config.json manualmente.")
    return WatchdogConfig()