#!/usr/bin/env python3
"""
Módulo de Configuração (config.py)
══════════════════════════════════════════════════════════════════
Responsável por definir, carregar e validar a configuração do 
WoFF Watchdog.

Utiliza Dataclasses para garantir um esquema rígido e seguro, 
evitando erros de KeyErrors caso o utilizador apague acidentalmente 
campos do ficheiro config.json.
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
    watch_paths: List[str] = field(default_factory=lambda: [
        "A:\\OBDSoftware\\WOFF\\campaigns",
        "A:\\OBDSoftware\\WOFF\\WoFF\\campaigns",
        "A:\\OBDSoftware\\WOFF\\log",
        "A:\\OBDSoftware\\WOFF\\WoFF\\log"
    ])
    export_path: str = "C:\\Users\\Public\\WoFFBase\\woff_export.json"
    watched_extensions: List[str] = field(default_factory=lambda: [".xml", ".txt", ".log"])
    stability_timeout_sec: float = 3.0
    stability_check_interval_sec: float = 0.15
    backup_export: bool = True
    discovery_log_path: str = "woff_discovery.log"
    log_level: str = "INFO"
    max_workers: int = 4
    export_schema_version: str = "1.4"

    @classmethod
    def from_dict(cls, d: dict) -> "WatchdogConfig":
        """Cria a configuração a partir de um dicionário, ignorando chaves inválidas."""
        valid = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**valid)

    def to_dict(self) -> dict:
        """Converte a configuração para dicionário (para guardar em JSON)."""
        return asdict(self)


def load_config(path: str) -> WatchdogConfig:
    """
    Carrega a configuração de um ficheiro JSON.
    Se o ficheiro não existir, cria-o com os valores padrão.
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
            log.warning(f"Erro ao ler config ({e}) — usando valores padrão.")
    else:
        try:
            default_cfg = WatchdogConfig()
            with open(p, "w", encoding="utf-8") as f:
                json.dump(default_cfg.to_dict(), f, indent=2, ensure_ascii=False)
            log.info(f"Ficheiro config.json criado — edita os caminhos conforme necessário.")
            return default_cfg
        except Exception as e:
            log.warning(f"Não foi possível escrever config.json: {e}")
    
    return WatchdogConfig()