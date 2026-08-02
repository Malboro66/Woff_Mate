#!/usr/bin/env python3
"""
Módulo de Normalização (normalization.py)
══════════════════════════════════════════════════════════════════
Contém as funções de lógica para limpar, padronizar e normalizar 
dados extraídos dos ficheiros XML e TXT do WoFF BHaH II.

As tabelas de mapeamento e expressões regulares estão importadas 
do módulo maps.py, garantindo uma separação clara entre dados 
estáticos e lógica de processamento.
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Optional

# Importar as tabelas estáticas e regex do maps.py
from .maps import (
    NATION_MAP, MISSION_TYPE_MAP, STATUS_PATTERNS, WOUND_RE, SEVERE_RE,
    VICTORY_TYPE_MAP, MONTHS_MAP
)

log = logging.getLogger("WoFFWatch")


def _map(raw: str, mapping: dict, fallback: str = "") -> str:
    """Função genérica para procurar texto em dicionários de mapeamento."""
    if not raw:
        return fallback
    raw_l = raw.strip().lower()
    for keys, value in mapping.items():
        if isinstance(keys, tuple):
            if any(k in raw_l for k in keys):
                return value
        elif keys in raw_l:
            return value
    # Corrigido: Retorna o fallback em vez de raw.strip()
    return fallback


def normalize_nation(raw: str) -> str:
    return _map(raw, NATION_MAP, "RFC")


def normalize_mission_type(raw: str) -> str:
    # Corrigido: Passa o texto original limpo como fallback
    return _map(raw, MISSION_TYPE_MAP, raw.strip() if raw else "")


def normalize_status(raw: str, root: Optional[ET.Element] = None) -> str:
    if not raw:
        return "Active"
    
    for pattern, status in STATUS_PATTERNS:
        if pattern.search(raw):
            return status
            
    if WOUND_RE.search(raw):
        severity = ""
        if root is not None:
            sev_elem = root.find(".//WoundSeverity")
            if sev_elem is None:
                sev_elem = root.find(".//Severity")
            # Corrigido: evita o DeprecationWarning do Python 3.14
            if sev_elem is not None and sev_elem.text:
                severity = sev_elem.text.lower()
        if SEVERE_RE.search(severity):
            return "Seriously Wounded"
        return "Lightly Wounded"
        
    return "Active"


def normalize_victory_type(raw: str) -> str:
    return _map(raw, VICTORY_TYPE_MAP, "Out of Control (OOC)")


def normalize_date(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    
    m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$", raw)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
        
    m = re.match(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})$", raw)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
        
    raw_l = raw.lower()
    for name, num in MONTHS_MAP.items():
        if name in raw_l:
            nums = [int(n) for n in re.findall(r"\d+", raw)]
            year  = next((n for n in nums if n > 100), None)
            day   = next((n for n in nums if 1 <= n <= 31), None)
            if year and day:
                return f"{year}-{str(num).zfill(2)}-{str(day).zfill(2)}"
                
    log.debug(f"Data não reconhecida para normalização: '{raw}'")
    return raw

# ──────────────────────────────────────────────────────────────
# CONVERSÃO DE COORDENADAS (Para mapas na Fase 3)
# ──────────────────────────────────────────────────────────────

def normalize_coordinates(raw: str) -> Optional[float]:
    """
    Converte o formato de coordenadas do WoFF (ex: N50*23'34.6102") 
    para graus decimais (ex: 50.3928339), ideal para APIs de mapas.
    Suporta N, S, E, W.
    """
    if not raw:
        return None
        
    raw = raw.strip().upper()
    
    # Regex para extrair Direção, Graus, Minutos e Segundos
    # Exemplo de match: N50*23'34.6102" ou E2*36'50.609
    match = re.match(r"^([NSEW])(\d{1,3})\*(\d{1,2})'(\d{1,2}(?:\.\d+)?)[\"\u201d]?$", raw)
    if not match:
        log.debug(f"Coordenada não reconhecida: '{raw}'")
        return None
        
    direction, deg_str, min_str, sec_str = match.groups()
    
    try:
        degrees = float(deg_str)
        minutes = float(min_str)
        seconds = float(sec_str)
        
        # Fórmula de conversão DMS para Decimal
        decimal_degrees = degrees + (minutes / 60.0) + (seconds / 3600.0)
        
        # Sul e Oeste são negativos
        if direction in ('S', 'W'):
            decimal_degrees *= -1
            
        return round(decimal_degrees, 6) # Precisão de 6 casas é suficiente para mapas
        
    except ValueError as e:
        log.warning(f"Erro ao converter coordenada '{raw}': {e}")
        return None