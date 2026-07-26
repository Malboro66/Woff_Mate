#!/usr/bin/env python3
"""
WoFF Journal Editor
══════════════════════════════════════════════════════════════════
Ferramenta que permite ao utilizador editar o seu Diário de Bordo.
Exporta o diário para um ficheiro de texto, abre o editor padrão,
e importa as alterações de volta para a Base de Dados.
══════════════════════════════════════════════════════════════════
"""
import os
import sys
import sqlite3
import json
import subprocess
import platform
import tempfile
import argparse

def get_db_path():
    config_path = "config.json"
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return cfg.get("export_path", "woff_data.db")
    return "woff_data.db"

def export_diary_to_file(conn, pilot_name: str, filepath: str):
    cursor = conn.execute("""
        SELECT d.id, d.entry_date, d.narrative
        FROM diary_entries d
        JOIN pilots p ON d.pilotId = p.id
        WHERE p.name = ?
        ORDER BY d.entry_date ASC
    """, (pilot_name,))
    entries = cursor.fetchall()
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"DIÁRIO DE BORDO DE {pilot_name.upper()}\n")
        f.write("INSTRUÇÕES: Edite o texto livremente. Para APAGAR uma entrada, apague o bloco inteiro (incluindo as linhas === ID === e DATA). Guarde e feche o ficheiro para aplicar as alterações.\n")
        f.write("=" * 60 + "\n")
        for entry in entries:
            f.write(f"=== ID: {entry['id']} ===\n")
            f.write(f"DATA: {entry['entry_date']}\n")
            f.write(f"{entry['narrative']}\n")
            f.write("=" * 60 + "\n")

def import_diary_from_file(conn, filepath: str):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Apagar todas as entradas existentes (serão substituídas pelas do ficheiro)
    cursor = conn.cursor()
    
    # Extrair blocos
    blocks = content.split("=" * 60)[1:] # Ignora o cabeçalho inicial
    
    imported_ids = set()
    for block in blocks:
        block = block.strip()
        if not block: continue
        
        lines = block.split("\n")
        entry_id = None
        entry_date = ""
        narrative_lines = []
        parsing_narrative = False
        
        for line in lines:
            if line.startswith("=== ID:"):
                entry_id = line.replace("=== ID:", "").replace("===", "").strip()
                parsing_narrative = False
            elif line.startswith("DATA:"):
                entry_date = line.replace("DATA:", "").strip()
                parsing_narrative = True
            elif parsing_narrative:
                narrative_lines.append(line)
                
        if entry_id and entry_date is not None:
            narrative = "\n".join(narrative_lines).strip()
            if narrative: # Não importar entradas vazias (apagadas pelo utilizador)
                imported_ids.add(entry_id)
                # UPSERT: Atualiza se existir, insere se for novo
                cursor.execute("""
                    INSERT INTO diary_entries (id, pilotId, missionId, entry_date, narrative)
                    VALUES (?, (SELECT id FROM pilots LIMIT 1), NULL, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET 
                        entry_date=excluded.entry_date, 
                        narrative=excluded.narrative
                """, (entry_id, entry_date, narrative))

    # Apagar entradas que estavam na DB mas não foram importadas (ou seja, o utilizador apagou-as)
    cursor.execute("DELETE FROM diary_entries WHERE id NOT IN ({})".format(",".join("?" * len(imported_ids))), tuple(imported_ids))
    conn.commit()

def open_editor(filepath: str):
    system = platform.system()
    if system == "Windows":
        os.startfile(filepath)
    elif system == "Darwin": # macOS
        subprocess.call(["open", filepath])
    else: # Linux
        subprocess.call(["xdg-open", filepath])
    
    input(f"\nPressione ENTER quando terminar de editar e guardar o ficheiro...")

def main():
    ap = argparse.ArgumentParser(description="WoFF Journal Editor - Editar o Diário de Bordo")
    ap.add_argument("--pilot", required=True, help="Nome do piloto")
    ap.add_argument("--db", default=None, help="Caminho direto para a base de dados SQLite")
    args = ap.parse_args()

    db_path = args.db if args.db else get_db_path()
    if not os.path.exists(db_path):
        print(f"[ERRO] Base de dados não encontrada: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Verificar se o piloto existe
    cursor = conn.execute("SELECT id FROM pilots WHERE name = ?", (args.pilot,))
    if not cursor.fetchone():
        print(f"[ERRO] Piloto '{args.pilot}' não encontrado.")
        sys.exit(1)

    # Criar ficheiro temporário
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".txt", delete=False, encoding="utf-8") as tmp:
        tmp_path = tmp.name

    try:
        print(f"A exportar diário de {args.pilot} para {tmp_path}...")
        export_diary_to_file(conn, args.pilot, tmp_path)
        
        print("A abrir o editor de texto...")
        open_editor(tmp_path)
        
        print("A importar alterações do ficheiro...")
        import_diary_from_file(conn, tmp_path)
        print("✓ Diário atualizado com sucesso na Base de Dados!")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        conn.close()

if __name__ == "__main__":
    main()