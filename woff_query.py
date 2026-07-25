#!/usr/bin/env python3
"""
WoFF Query Tool (CLI)
══════════════════════════════════════════════════════════════════
Ferramenta de linha de comando para consultar os dados extraídos 
pelo WoFF Watchdog. Lê diretamente da Base de Dados SQLite.
══════════════════════════════════════════════════════════════════
"""
import os
import sys
import json
import csv
import sqlite3
import argparse
import textwrap

class Colors:
    """Gestão de cores ANSI. Desativadas automaticamente se não for um TTY."""
    def __init__(self, enabled: bool = True):
        if enabled:
            self.HEADER = '\033[95m'
            self.BLUE = '\033[94m'
            self.CYAN = '\033[96m'
            self.GREEN = '\033[92m'
            self.YELLOW = '\033[93m'
            self.RED = '\033[91m'
            self.RESET = '\033[0m'
            self.BOLD = '\033[1m'
        else:
            self.HEADER = ''
            self.BLUE = ''
            self.CYAN = ''
            self.GREEN = ''
            self.YELLOW = ''
            self.RED = ''
            self.RESET = ''
            self.BOLD = ''

def get_color(c: Colors, value: int, warn: int, danger: int, reverse: bool = False) -> str:
    if reverse:
        if value <= danger: return c.RED
        if value <= warn: return c.YELLOW
        return c.GREEN
    else:
        if value >= danger: return c.RED
        if value >= warn: return c.YELLOW
        return c.GREEN

def get_db_path(config_path: str, db_path: str) -> str:
    if db_path: return db_path
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return cfg.get("export_path", "woff_data.db")
        except Exception: pass
    return "woff_data.db"

def connect_db(db_path: str) -> sqlite3.Connection:
    """Cria e retorna a ligação. Lança exceções em caso de erro."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Base de dados não encontrada: {db_path}")
        
    # Lança sqlite3.Error naturalmente se não conseguir ligar
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def export_data(data: list, format_type: str, headers: list):
    """Exporta dados para JSON, CSV ou Markdown."""
    if not data:
        print("Sem dados para exportar.")
        return

    if format_type == "json":
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif format_type == "csv":
        writer = csv.DictWriter(sys.stdout, fieldnames=headers, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(data)
    elif format_type == "md":
        print(f"| {' | '.join(headers)} |")
        print(f"|{'---|' * len(headers)}")
        for row in data:
            vals = [str(row.get(h, "")) for h in headers]
            print(f"| {' | '.join(vals)} |")

def list_pilots(conn, c: Colors, args):
    cursor = conn.execute("SELECT name, rank, squadron, status, missions, killsCount FROM pilots ORDER BY name")
    pilots = [dict(row) for row in cursor.fetchall()]
    
    if args.format != "table":
        export_data(pilots, args.format, ["name", "rank", "squadron", "status", "missions", "killsCount"])
        return

    print(f"\n{c.HEADER}{c.BOLD}✈ Lista de Pilotos{c.RESET}")
    print("-" * 60)
    if not pilots:
        print(f"{c.YELLOW}Nenhum piloto encontrado na base de dados.{c.RESET}")
        return
        
    for p in pilots:
        status_color = c.GREEN if p["status"] in ("Active", "In Service") else c.RED
        print(f"{c.BOLD}{p['name']}{c.RESET} ({p['rank']})")
        print(f"  Esquadrão: {p['squadron']} | Status: {status_color}{p['status']}{c.RESET}")
        print(f"  Missões: {p['missions']} | Vitórias: {p['killsCount']}")
        print()

def show_pilot_details(conn, pilot_name, c: Colors) -> bool:
    cursor = conn.execute("SELECT * FROM pilots WHERE name = ?", (pilot_name,))
    p = cursor.fetchone()
    
    if not p:
        print(f"{c.RED}Piloto '{pilot_name}' não encontrado.{c.RESET}")
        return False
        
    print(f"\n{c.HEADER}{c.BOLD}🧑‍✈️ Perfil do Piloto{c.RESET}")
    print("-" * 60)
    print(f"{c.BOLD}Nome:{c.RESET} {p['name']}")
    print(f"{c.BOLD}Nação:{c.RESET} {p['nation']}")
    print(f"{c.BOLD}Patente:{c.RESET} {p['rank']}")
    print(f"{c.BOLD}Esquadrão:{c.RESET} {p['squadron']}")
    print(f"{c.BOLD}Aeronave:{c.RESET} {p['aircraft']}")
    print(f"{c.BOLD}Base:{c.RESET} {p['aerodrome']} ({p['sector']})")
    print(f"{c.BOLD}Status:{c.RESET} {p['status']}")
    print(f"{c.BOLD}Data Nasc.:{c.RESET} {p['birthDate']} em {p['birthPlace']}")
    print(f"{c.BOLD}Foto ID:{c.RESET} {p['photo']}")
    print(f"\n{c.CYAN}Estatísticas de Carreira:{c.RESET}")
    print(f"  Missões voadas: {p['missions']}")
    print(f"  Minutos de voo: {p['flminutes']}")
    print(f"  Vitórias confirmadas: {p['killsCount']}")
    print(f"  Reclamações: {p['claimsCount']}")
    print(f"  Skill: {p['skill']} | Reputação: {p['reputation']}")
    return True

def show_rpg_stats(conn, pilot_name, c: Colors):
    cursor = conn.execute("SELECT id FROM pilots WHERE name = ?", (pilot_name,))
    row = cursor.fetchone()
    if not row: return
    pilot_id = row["id"]
    
    cursor = conn.execute("SELECT * FROM pilot_rpg_stats WHERE pilotId = ?", (pilot_id,))
    stats = cursor.fetchone()
    
    print(f"\n{c.CYAN}🧠 Estado RPG (Fase 2){c.RESET}")
    print("-" * 60)
    if not stats:
        print("  Sem dados de RPG calculados.")
        return
        
    fatigue, morale, stress = stats["fatigue"], stats["morale"], stats["stress"]
    
    f_color = get_color(c, fatigue, 40, 70)
    m_color = get_color(c, morale, 60, 30, reverse=True)
    s_color = get_color(c, stress, 40, 70)
    
    print(f"  Fadiga : {f_color}{fatigue}/100{c.RESET} {'█' * (fatigue // 10)}")
    print(f"  Moral  : {m_color}{morale}/100{c.RESET} {'█' * (morale // 10)}")
    print(f"  Stress : {s_color}{stress}/100{c.RESET} {'█' * (stress // 10)}")
    print(f"  Atualizado: {stats['last_updated']}")

def show_missions(conn, pilot_name, c: Colors, args):
    query = """
        SELECT m.date, m.time, m.missionType, m.aircraft, m.result, m.damageReceived, m.woundsReceived
        FROM missions m
        JOIN pilots p ON m.pilotId = p.id
        WHERE p.name = ?
    """
    params = [pilot_name]
    
    if args.since:
        query += " AND m.date >= ?"
        params.append(args.since)
    if args.type:
        query += " AND m.missionType LIKE ?"
        params.append(f"%{args.type}%")
    if args.result:
        query += " AND m.result LIKE ?"
        params.append(f"%{args.result}%")
        
    query += " ORDER BY m.date DESC, m.time DESC LIMIT ?"
    params.append(args.limit)
    
    cursor = conn.execute(query, params)
    missions = [dict(row) for row in cursor.fetchall()]
    
    if args.format != "table":
        export_data(missions, args.format, ["date", "time", "missionType", "aircraft", "result", "damageReceived", "woundsReceived"])
        return

    print(f"\n{c.CYAN}📜 Missões (Filtrado: {len(missions)} resultados){c.RESET}")
    print("-" * 60)
    if not missions:
        print("  Nenhuma missão encontrada com os filtros especificados.")
        return
        
    for m in missions:
        dmg = f" {c.RED}[Danos]{c.RESET}" if m["damageReceived"] == 1 else ""
        wnd = f" {c.RED}[Ferido]{c.RESET}" if m["woundsReceived"] == 1 else ""
        print(f"  [{m['date']} {m['time']}] {m['missionType']} ({m['aircraft']}){dmg}{wnd}")
        print(f"    Resultado: {m['result']}")

def show_diary(conn, pilot_name, c: Colors, args):
    query = """
        SELECT d.entry_date, d.narrative
        FROM diary_entries d
        JOIN pilots p ON d.pilotId = p.id
        WHERE p.name = ?
    """
    params = [pilot_name]
    
    if args.since:
        query += " AND d.entry_date >= ?"
        params.append(args.since)
        
    query += " ORDER BY d.entry_date DESC LIMIT ?"
    params.append(args.limit)
    
    cursor = conn.execute(query, params)
    entries = [dict(row) for row in cursor.fetchall()]
    
    if args.format != "table":
        export_data(entries, args.format, ["entry_date", "narrative"])
        return

    print(f"\n{c.CYAN}📝 Diário de Bordo (Últimas {len(entries)} entradas){c.RESET}")
    print("=" * 60)
    if not entries:
        print("  Diário vazio.")
        return
        
    for d in entries:
        print(f"{c.YELLOW}{d['entry_date']}{c.RESET}")
        indented_narrative = textwrap.indent(d['narrative'], '  ')
        print(indented_narrative)
        print("-" * 60)

def show_wingmen(conn, pilot_name, c: Colors, args):
    cursor = conn.execute("""
        SELECT s.rank, s.fName, s.sName, s.status, s.skill, s.bio
        FROM squad_members s
        JOIN pilots p ON s.pilotId = p.id
        WHERE p.name = ?
    """, (pilot_name,))
    wingmen = [dict(row) for row in cursor.fetchall()]
    
    if args.format != "table":
        export_data(wingmen, args.format, ["rank", "fName", "sName", "status", "skill", "bio"])
        return

    print(f"\n{c.CYAN}👥 Membros do Esquadrão (AI){c.RESET}")
    print("-" * 60)
    if not wingmen:
        print("  Nenhum wingman encontrado.")
        return
        
    for w in wingmen:
        status_color = c.GREEN if w["status"] == "In Service" else c.RED
        print(f"  {w['rank']} {w['fName']} {w['sName']} (Skill: {w['skill']}) - {status_color}{w['status']}{c.RESET}")
        if w["bio"]:
            print(f"    Bio: {w['bio'][:80]}...")

def main():
    ap = argparse.ArgumentParser(description="WoFF Query Tool - Consulta a Base de Dados do WoFF Watchdog")
    ap.add_argument("--pilot", help="Nome do piloto a consultar")
    ap.add_argument("--missions", action="store_true", help="Mostrar histórico de missões do piloto")
    ap.add_argument("--diary", action="store_true", help="Mostrar o diário de bordo do piloto")
    ap.add_argument("--wingmen", action="store_true", help="Mostrar os membros do esquadrão (AI)")
    ap.add_argument("--config", default="config.json", help="Caminho para config.json")
    ap.add_argument("--db", default=None, help="Caminho direto para a base de dados SQLite")
    ap.add_argument("--no-color", action="store_true", help="Desativar cores ANSI no output")
    
    ap.add_argument("--limit", type=int, default=10, help="Número máximo de registos a mostrar (padrão: 10)")
    ap.add_argument("--since", help="Filtrar registos a partir desta data (Formato: YYYY-MM-DD)")
    ap.add_argument("--type", help="Filtrar missões por tipo (ex: Patrol, Bombing)")
    ap.add_argument("--result", help="Filtrar missões por resultado (ex: KIA, Damaged, Completed)")
    ap.add_argument("--format", choices=["table", "json", "csv", "md"], default="table", help="Formato de saída dos dados")
    
    args = ap.parse_args()

    use_color = sys.stdout.isatty() and not args.no_color
    c = Colors(enabled=use_color)
    conn = None

    try:
        db_path = get_db_path(args.config, args.db)
        conn = connect_db(db_path)

        if not args.pilot:
            list_pilots(conn, c, args)
            print(f"\nPara ver detalhes de um piloto, use: python woff_query.py --pilot \"Nome do Piloto\"")
        else:
            if args.format == "table":
                found = show_pilot_details(conn, args.pilot, c)
                if found:
                    show_rpg_stats(conn, args.pilot, c)
            else:
                found = True

            if found:
                if args.missions:
                    show_missions(conn, args.pilot, c, args)
                if args.wingmen:
                    show_wingmen(conn, args.pilot, c, args)
                if args.diary:
                    show_diary(conn, args.pilot, c, args)
                    
            if args.format == "table" and not (args.missions or args.wingmen or args.diary):
                print(f"\n{c.YELLOW}Dica: Adiciona --missions, --wingmen ou --diary para ver mais detalhes.{c.RESET}")
                
    except FileNotFoundError as e:
        print(f"\n{c.RED}[ERRO] {e}{c.RESET}")
        print("Certifica-te que o WoFF Watchdog já correu e gerou a base de dados.")
    except sqlite3.Error as e:
        print(f"\n{c.RED}[ERRO SQL] Ocorreu um erro ao consultar a base de dados: {e}{c.RESET}")
        print("Isto pode acontecer se o WoFF Watchdog estiver a escrever na base de dados neste momento. Tenta novamente dentro de alguns segundos.")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()