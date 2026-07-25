#!/usr/bin/env python3
"""
Modelos de Dados (models.py)
══════════════════════════════════════════════════════════════════
"""

import uuid
from dataclasses import dataclass, field
from typing import List

def _uid() -> str:
    return uuid.uuid4().hex[:12]

@dataclass
class WoFFPilot:
    """Representa os dados de um piloto na campanha."""
    id:           str = field(default_factory=_uid)
    name:         str = ""
    fName:        str = ""
    sName:        str = ""
    nation:       str = ""
    rank:         str = ""
    squadron:     str = ""
    aircraft:     str = ""
    aerodrome:    str = ""
    sector:       str = ""
    startDate:    str = ""
    enlisted:     str = "" 
    status:       str = "Active"
    notes:        str = ""
    photo:        str = ""
    
    # Estatísticas extraídas do Dossier
    birthDate:    str = ""
    birthPlace:   str = ""
    missions:     str = "0"
    flminutes:    str = "0"
    claimsCount:  str = "0"
    killsCount:   str = "0"
    skill:        str = "0"
    reputation:   str = "0"
    
    source_file:  str = ""
    last_updated: str = ""

@dataclass
class WoFFMission:
    id:             str  = field(default_factory=_uid)
    pilotId:        str  = ""
    date:           str  = ""
    time:           str  = "" # ADICIONADO: Para deduplicação correta
    missionType:    str  = ""
    aircraft:       str  = ""
    duration:       str  = ""
    altitude:       str  = ""
    sector:         str  = ""
    squadron:       str  = ""
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
    sector:      str  = ""
    aircraft:    str  = ""
    source_file: str  = ""

@dataclass
class WoFFDecoration:
    id:          str = field(default_factory=_uid)
    pilotId:     str = ""
    name:        str = ""
    date:        str = ""
    citation:    str = ""
    source_file: str = ""

@dataclass
class WoFFWingman:
    id:          str = field(default_factory=_uid)
    pilotId:     str = ""
    rank:        str = ""
    fName:       str = ""
    sName:       str = ""
    skill:       str = "0"
    morale:      str = "0"
    status:      str = "Active"
    missions:    str = "0"
    flminutes:   str = "0"
    bio:         str = ""