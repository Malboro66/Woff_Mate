#!/usr/bin/env python3
"""
Catalogador de Esquadrões (squadron_cataloger.py)
══════════════════════════════════════════════════════════════════
Lê a pasta Scratchpad do jogo, desofusca os ficheiros .txt dos 
esquadrões e popula a tabela 'squadrons' na Base de Dados.
══════════════════════════════════════════════════════════════════
"""
import os
import sqlite3
import logging

log = logging.getLogger("WoFFWatch")

from woff.decode.common import unscramble

def catalog_squadrons(scratchpad_dir: str, db_path: str):
    if not os.path.exists(scratchpad_dir):
        log.warning(f"Pasta Scratchpad não encontrada: {scratchpad_dir}")
        return

    log.info(f"A catalogar esquadrões de: {scratchpad_dir}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Criar tabela de esquadrões se não existir
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS squadrons (
            id TEXT PRIMARY KEY,
            name TEXT,
            raw_data TEXT,
            source_file TEXT
        )
    """)

    count = 0
    for filename in os.listdir(scratchpad_dir):
        if filename.lower().endswith(".txt"):
            filepath = os.path.join(scratchpad_dir, filename)
            squad_id = os.path.splitext(filename)[0] # Ex: "Esc 15"
            
            try:
                with open(filepath, "rb") as f:
                    raw_bytes = f.read()
                
                # Desofuscar
                real_data = unscramble(raw_bytes)
                raw_hex = real_data.hex()
                
                # Por agora, guardamos o ID e os dados brutos. 
                # Mais tarde podemos mapear os bytes para nome/cores.
                cursor.execute("""
                    INSERT OR REPLACE INTO squadrons (id, name, raw_data, source_file)
                    VALUES (?, ?, ?, ?)
                """, (squad_id, squad_id, raw_hex, filename))
                count += 1
                
            except Exception as e:
                log.error(f"Erro ao ler esquadrão {filename}: {e}")

    conn.commit()
    conn.close()
    log.info(f"✓ {count} esquadrões catalogados na base de dados.")