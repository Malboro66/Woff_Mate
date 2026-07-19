#!/usr/bin/env python3
"""
Catalogador de Medalhas (medal_cataloger.py)
══════════════════════════════════════════════════════════════════
Lê a pasta de imagens de medalhas do jogo e popula a tabela 
'medals_catalog' na Base de Dados SQLite.
Permite que a app saiba que medalhas existem e associe os ícones.
══════════════════════════════════════════════════════════════════
"""

import os
import re
import sqlite3
import logging

log = logging.getLogger("WoFFWatch")

def catalog_medals(medals_dir: str, db_path: str):
    if not os.path.exists(medals_dir):
        log.warning(f"Diretório de medalhas não encontrado: {medals_dir}")
        return

    log.info(f"A catalogar medalhas de: {medals_dir}")
    
    # Regex para extrair "(País) Nome.bmp"
    pattern = re.compile(r"\((.*?)\)\s*(.*?)\.bmp", re.IGNORECASE)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Criar tabela se não existir
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medals_catalog (
            id TEXT PRIMARY KEY,
            country TEXT,
            name TEXT,
            filename TEXT,
            UNIQUE(country, name)
        )
    """)

    count = 0
    for filename in os.listdir(medals_dir):
        if filename.lower().endswith(".bmp"):
            match = pattern.match(filename)
            if match:
                country = match.group(1).strip()
                name = match.group(2).strip()
                medal_id = f"{country}_{name}".replace(" ", "_").lower()
                
                cursor.execute("""
                    INSERT OR IGNORE INTO medals_catalog (id, country, name, filename)
                    VALUES (?, ?, ?, ?)
                """, (medal_id, country, name, filename))
                count += cursor.rowcount

    conn.commit()
    conn.close()
    log.info(f"✓ {count} medalhas novas catalogadas na base de dados.")