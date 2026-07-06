#!/usr/bin/env python3
"""
Tabelas de Mapeamento (maps.py)
══════════════════════════════════════════════════════════════════
Contém todas as tabelas de tradução, dicionários e expressões 
regulares estáticas usadas para normalizar os dados extraídos 
dos ficheiros do WoFF BHaH II.

Manter estes dados isolados facilita a atualização de traduções 
ou a adaptação a novas versões do jogo sem alterar a lógica do código.
══════════════════════════════════════════════════════════════════
"""

import re

# ──────────────────────────────────────────────────────────────
# MAPEAMENTO DE NAÇÕES
# ──────────────────────────────────────────────────────────────

NATION_MAP = {
    "rfc": "RFC", "royal flying corps": "RFC", "british": "RFC", "uk": "RFC",
    "rnas": "RNAS", "royal naval air service": "RNAS", "naval": "RNAS",
    "raf": "RAF", "royal air force": "RAF",
    "french": "French", "france": "French", "aeronautique": "French", "fr": "French",
    "german": "German", "germany": "German", "luftstreitkrafte": "German",
    "deutsche": "German", "de": "German",
    "american": "American", "usas": "American", "usa": "American", "us": "American",
    "belgian": "Belgian", "belgium": "Belgian", "belge": "Belgian",
}

# ──────────────────────────────────────────────────────────────
# MAPEAMENTO DE TIPOS DE MISSÃO
# ──────────────────────────────────────────────────────────────

MISSION_TYPE_MAP = {
    "offensive patrol": "Offensive Patrol (OP)", "op": "Offensive Patrol (OP)",
    "defensive patrol": "Defensive Patrol",
    "close air support": "Close Air Support (CAS)", "cas": "Close Air Support (CAS)",
    "artillery": "Artillery Observation (Art.Obs.)", "art. obs": "Artillery Observation (Art.Obs.)",
    "photographic": "Photographic Reconnaissance", "photo recon": "Photographic Reconnaissance",
    "strategic recon": "Strategic Reconnaissance", "long.range recon": "Strategic Reconnaissance",
    "bombing": "Bombing Raid (Tactical)", "bomb": "Bombing Raid (Tactical)",
    "balloon": "Balloon Busting",
    "escort": "Escort Duty",
    "ground attack": "Ground Attack / Strafing", "straf": "Ground Attack / Strafing",
}

# ──────────────────────────────────────────────────────────────
# MAPEAMENTO DE ESTADO DO PILOOTO (STATUS)
# Usamos regex com \b (word boundaries) para evitar falsos positivos
# Ex: "deadline" já não ativa o status "dead"
# ──────────────────────────────────────────────────────────────

STATUS_PATTERNS = [
    (re.compile(r"\b(kia|killed|mort|tot|deceased)\b", re.I), "KIA"),
    (re.compile(r"\b(pow|prisoner|captured|prisonnier)\b", re.I), "PoW"),
    (re.compile(r"\bmia\b|\bmissing\b", re.I), "MIA"),
    (re.compile(r"\b(invalided|retired|discharged)\b", re.I), "Invalided Out"),
    (re.compile(r"\b(survived|end\s+of\s+war)\b", re.I), "Survived War"),
]

WOUND_RE = re.compile(r"\b(wound|wounded|hospital|injured|bless)", re.I)
SEVERE_RE = re.compile(r"\b(serious|severe|critical|heavy|grave)\b", re.I)

# ──────────────────────────────────────────────────────────────
# MAPEAMENTO DE TIPOS DE VITÓRIAS
# ──────────────────────────────────────────────────────────────

VICTORY_TYPE_MAP = {
    ("flame", "fire", "burned", "flamme"):           "Destroyed — In Flames",
    ("structural", "break", "broke apart", "broke"): "Destroyed — Structural Failure",
    ("ooc", "out of control", "spin"):               "Out of Control (OOC)",
    ("forced to land", "force land", "landed"):      "Forced to Land",
    ("driven down", "driven"):                       "Driven Down (Unconfirmed)",
    ("balloon", "drachen", "caquot"):                "Balloon Destroyed (Flames)",
}

# ──────────────────────────────────────────────────────────────
# MAPEAMENTO DE MESES (PARA NORMALIZAÇÃO DE DATAS)
# Suporta Inglês e Francês
# ──────────────────────────────────────────────────────────────

MONTHS_MAP = {
    # Inglês (Extenso)
    "january":1, "february":2, "march":3, "april":4, "may":5, "june":6,
    "july":7, "august":8, "september":9, "october":10, "november":11, "december":12,
    # Inglês (Abreviado)
    "jan":1, "feb":2, "mar":3, "apr":4, "jun":6, "jul":7, "aug":8,
    "sep":9, "oct":10, "nov":11, "dec":12,
    # Francês
    "janvier":1, "février":2, "mars":3, "avril":4, "mai":5, "juin":6,
    "juillet":7, "août":8, "septembre":9, "octobre":10, "novembre":11, "décembre":12,
}

# ──────────────────────────────────────────────────────────────
# EXPRESSÕES REGULARES PARA PARSER DE TEXTO (DEBRIEFING)
# ──────────────────────────────────────────────────────────────

DEBRIEF_REGEX = {
    "DATE": re.compile(
        r"(?:date|mission\s*date|sortie\s*date)[:\s]+"
        r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4}"
        r"|\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2}"
        r"|\d{1,2}\s+\w+\s+\d{4})",
        re.IGNORECASE
    ),
    "TYPE": re.compile(r"(?:mission\s*type|order|sortie\s*type|type)[:\s]+([\w\s\(\)/\-]+?)(?:\n|,|\.)", re.IGNORECASE),
    "DURATION": re.compile(r"(?:duration|flight\s*time|hours)[:\s]+(\d+(?:[.,]\d+)?)\s*(?:h(?:ours?|r)?)?", re.IGNORECASE),
    "AIRCRAFT": re.compile(r"(?:aircraft|plane|flying|flew)[:\s]+([\w\s\.\-]+?)(?:\n|,|\.)", re.IGNORECASE),
    "SECTOR": re.compile(r"(?:sector|area|region|front)[:\s]+([\w\s\-]+?)(?:\n|,|\.)", re.IGNORECASE),
    "CONTACTS": re.compile(r"(?:enemy\s*contact|hostile|encountered?)[:\s]+(\d+)", re.IGNORECASE),
    "CLAIMS": re.compile(r"(?:claim|kill|victory|abschuss)[:\s]+(\d+)", re.IGNORECASE),
    
    # Regex para vitórias em texto (quantificador {3,50} corrigido)
    "KILL": re.compile(
        r"(?:destroyed|shot\s+down|forced\s+to\s+land|out\s+of\s+control|OOC|driven\s+down)"
        r"\s*([\w\s\.\-]{3,50})"
        r"(?:\s+(?:in\s+flames?|ooc|structural|forced))?",
        re.IGNORECASE
    ),
    "TIME": re.compile(r"(\d{1,2}:\d{2})")
}