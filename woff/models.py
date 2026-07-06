#!/usr/bin/env python3
"""
Modelos de Dados (models.py)
══════════════════════════════════════════════════════════════════
Contém as estruturas de dados (dataclasses) que representam a 
informação extraída dos ficheiros do WoFF e exportada para a 
aplicação WoFFBase.

A utilização de dataclasses garante:
- Tipagem forte (type hints) para melhor manutenção.
- Geração automática de construtores (__init__) e representações (__repr__).
- Conversão direta para dicionários (asdict) para exportação JSON.
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import List


def _uid() -> str:
    """Gera um identificador único curto (12 caracteres hex)."""
    return uuid.uuid4().hex[:12]


@dataclass
class WoFFPilot:
    """Representa os dados de um piloto na campanha."""
    id:           str = field(default_factory=_uid)
    name:         str = ""
    nation:       str = ""
    rank:         str = ""
    squadron:     str = ""
    aircraft:     str = ""
    aerodrome:    str = ""
    sector:       str = ""
    startDate:    str = ""
    status:       str = "Active"
    notes:        str = ""
    source_file:  str = ""
    last_updated: str = ""


@dataclass
class WoFFMission:
    """Representa uma missão individual (sortie) voada pelo piloto."""
    id:             str  = field(default_factory=_uid)
    pilotId:        str  = ""
    date:           str  = ""
    missionType:    str  = ""
    aircraft:       str  = ""
    duration:       str  = ""
    altitude:       str  = ""
    sector:         str  = ""
    weather:        str  = ""
    enemyContacts:  str  = "0"
    claimsCount:    str  = "0"
    result:         str  = ""
    damageReceived: bool = False
    woundsReceived: bool = False
    notes:          str  = ""
    source_file:    str  = ""


@dataclass
class WoFFVictory:
    """Representa uma vitória (claim/kill) reportada num combate."""
    id:          str  = field(default_factory=_uid)
    pilotId:     str  = ""
    date:        str  = ""
    time:        str  = ""
    missionId:   str  = ""
    enemyType:   str  = ""
    victoryType: str  = ""
    location:    str  = ""
    confirmed:   bool = False
    witnesses:   str  = ""
    notes:       str  = ""
    source_file: str  = ""


@dataclass
class WoFFDecoration:
    """Representa uma condecoração ou medalha atribuída ao piloto."""
    id:          str = field(default_factory=_uid)
    pilotId:     str = ""
    name:        str = ""
    date:        str = ""
    citation:    str = ""
    source_file: str = ""


@dataclass
class WoFFExport:
    """
    Estrutura raiz exportada — compatível com o WoFFBase app.
    Este dicionário é o que é serializado para o ficheiro JSON final.
    """
    pilots:      List[dict] = field(default_factory=list)
    missions:    List[dict] = field(default_factory=list)
    victories:   List[dict] = field(default_factory=list)
    decorations: List[dict] = field(default_factory=list)
    diary:       List[dict] = field(default_factory=list)
    meta:        dict       = field(default_factory=dict)