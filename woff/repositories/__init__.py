#!/usr/bin/env python3
"""
Pacote de Repositórios (repositories/)
══════════════════════════════════════════════════════════════════
Separação de responsabilidades da camada de persistência.
Cada repositório gere uma entidade de domínio.
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

from .pilot import PilotRepository
from .mission import MissionRepository
from .rpg import RpgRepository
from .wingman import WingmanRepository

__all__ = [
    "PilotRepository",
    "MissionRepository",
    "RpgRepository",
    "WingmanRepository",
]