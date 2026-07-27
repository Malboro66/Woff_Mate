#!/usr/bin/env python3
"""
diagnostico.py — Auditoria da Base de Dados WoFF
══════════════════════════════════════════════════════════════════
Correr: python diagnostico.py
══════════════════════════════════════════════════════════════════
"""
import sys
import os
import sqlite3

# Ajusta se o teu config.json estiver noutro sítio
DB_PATH = os.path.expanduser("~/Documents/WoFFBase/woff_data.db")
if not os.path.exists(DB_PATH):
    DB_PATH = "woff_data.db"  # fallback

if not os.path.exists(DB_PATH):
    print(f"[ERRO] Base de dados não encontrada: {DB_PATH}")
    sys.exit(1)

print(f"📊 A auditar: {DB_PATH}\n")
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# ── 1. PILOTOS ──
print("═" * 60)
print("1. TABELA: pilots")
print("─" * 60)
c.execute("SELECT id, name, squadron, status, missions, flminutes, skill, killsCount FROM pilots")
pilots = c.fetchall()
if not pilots:
    print("  ⚠ Nenhum piloto encontrado!")
else:
    for p in pilots:
        print(f"  ID={p['id']} | Nome={p['name']} | Esquadrão={p['squadron']} | "
              f"Status={p['status']} | Missões={p['missions']} | Min={p['flminutes']} | "
              f"Skill={p['skill']} | Kills={p['killsCount']}")

# ── 2. MISSÕES ──
print("\n" + "═" * 60)
print("2. TABELA: missions (últimas 5)")
print("─" * 60)
c.execute("SELECT id, pilotId, date, time, missionType, aircraft, squadron FROM missions ORDER BY date DESC, time DESC LIMIT 5")
missions = c.fetchall()
if not missions:
    print("  ⚠ Nenhuma missão encontrada!")
else:
    for m in missions:
        print(f"  ID={m['id']} | pilotId={m['pilotId']} | Data={m['date']} {m['time']} | "
              f"Tipo={m['missionType']} | Avião={m['aircraft']} | Sqn={m['squadron']}")

# ── 3. VERIFICAR COERÊNCIA pilotId ──
print("\n" + "═" * 60)
print("3. COERÊNCIA: Missões órfãs (pilotId não existe em pilots)")
print("─" * 60)
c.execute("""
    SELECT m.id, m.pilotId, m.date 
    FROM missions m 
    LEFT JOIN pilots p ON m.pilotId = p.id 
    WHERE p.id IS NULL
""")
orphans = c.fetchall()
if orphans:
    print(f"  ⚠ {len(orphans)} missões com pilotId inválido!")
    for o in orphans:
        print(f"    Missão {o['id']} → pilotId={o['pilotId']} ({o['date']})")
else:
    print("  ✓ Todas as missões têm um piloto válido.")

# ── 4. RPG STATS ──
print("\n" + "═" * 60)
print("4. TABELA: pilot_rpg_stats")
print("─" * 60)
c.execute("SELECT pilotId, fatigue, morale, stress, last_updated FROM pilot_rpg_stats")
rpg = c.fetchall()
if not rpg:
    print("  ⚠ Nenhum stat RPG calculado!")
else:
    for r in rpg:
        print(f"  pilotId={r['pilotId']} | Fadiga={r['fatigue']} | Moral={r['morale']} | "
              f"Stress={r['stress']} | Atualizado={r['last_updated']}")

# ── 5. DIÁRIO ──
print("\n" + "═" * 60)
print("5. TABELA: diary_entries (últimas 10)")
print("─" * 60)
c.execute("SELECT id, pilotId, missionId, entry_date, narrative FROM diary_entries ORDER BY entry_date DESC LIMIT 10")
diary = c.fetchall()
if not diary:
    print("  ⚠ Nenhuma entrada de diário!")
else:
    for d in diary:
        prefix = "[MISSÃO]" if d['missionId'] else "[EVENTO]"
        print(f"  {prefix} {d['entry_date']} | pilotId={d['pilotId']}")
        print(f"    {d['narrative'][:80]}...")

# ── 6. WINGMEN ──
print("\n" + "═" * 60)
print("6. TABELA: squad_members (wingmen)")
print("─" * 60)
c.execute("SELECT pilotId, rank, fName, sName, status FROM squad_members LIMIT 10")
wingmen = c.fetchall()
if not wingmen:
    print("  ⚠ Nenhum wingman na base de dados!")
else:
    for w in wingmen:
        print(f"  pilotId={w['pilotId']} | {w['rank']} {w['fName']} {w['sName']} ({w['status']})")

# ── 7. RESUMO DE IDs ──
print("\n" + "═" * 60)
print("7. RESUMO DE IDs NA BASE DE DADOS")
print("─" * 60)
c.execute("SELECT id, name, source_file FROM pilots")
for p in c.fetchall():
    print(f"  Piloto: id={p['id']} | nome='{p['name']}' | ficheiro='{p['source_file']}'")

conn.close()
print("\n" + "═" * 60)
print("FIM DO DIAGNÓSTICO")