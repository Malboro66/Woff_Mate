#!/usr/bin/env python3
r"""
Utilitário de Registo do Windows (win_registry.py)
══════════════════════════════════════════════════════════════════
Equivalente ao WinRegistry.java do Pilot Log Editor.
Lê o Registo do Windows para descobrir automaticamente onde o 
WoFF BHaH II está instalado.
══════════════════════════════════════════════════════════════════
"""

import logging
from typing import Any, Optional, Protocol, Tuple, cast

log = logging.getLogger("WoFFWatch")

# Chave do registo usada pelo instalador do WoFF (OBD Software)
WOFF_REG_KEY = r"Software\VB and VBA Program Settings\OFFManager4\Settings"
WOFF_REG_VALUE = "CFS3Path"


class _WinReg(Protocol):
    """Subset of winreg used here, also type-checkable on non-Windows hosts."""

    HKEY_CURRENT_USER: int

    def OpenKey(self, key: int, sub_key: str) -> Any: ...
    def QueryValueEx(self, key: Any, value_name: str) -> Tuple[Any, int]: ...
    def CloseKey(self, key: Any) -> None: ...

def get_woff_install_path() -> Optional[str]:
    """
    Procura no Registo do Windows (HKEY_CURRENT_USER) o caminho de 
    instalação do WoFF BHaH II.
    """
    try:
        import winreg
    except ImportError:
        log.warning("Módulo 'winreg' não disponível (não está a correr em Windows).")
        return None

    registry = cast(_WinReg, winreg)

    try:
        # HKEY_CURRENT_USER = -2147483647 ou winreg.HKEY_CURRENT_USER
        key = registry.OpenKey(registry.HKEY_CURRENT_USER, WOFF_REG_KEY)
        path, _ = registry.QueryValueEx(key, WOFF_REG_VALUE)
        registry.CloseKey(key)
        
        if path:
            log.info(f"Caminho do WoFF encontrado no Registo: {path}")
            return path
    except FileNotFoundError:
        log.warning("Chave de registo do WoFF não encontrada. O jogo está instalado?")
    except Exception as e:
        log.error(f"Erro ao ler o Registo do Windows: {e}")
        
    return None
