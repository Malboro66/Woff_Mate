#!/usr/bin/env python3
"""
Gerador de Relatório de Extração (gerar_relatorio.py)
══════════════════════════════════════════════════════════════════
Lê os ficheiros reais do WoFF (baseado no config.json), extrai todas 
as informações possíveis e gera um ficheiro woff_data_report.txt 
mapeando a origem de cada dado.
══════════════════════════════════════════════════════════════════
"""
import os
import sys
import glob
import logging


from .config import load_config
from .parsers.dossier_parser import WoFFDossierParser
from .parsers.pilot_data_parser import WoFFPilotDataParser
from .parsers.mission_log_parser import WoFFMissionLogParser

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("ReportGen")

OUTPUT_FILE = "woff_data_report.txt"

def main():
    log.info("A iniciar geração de relatório...")
    
    # 1. Carregar caminhos dinamicamente do config.json
    cfg = load_config("config.json")
    valid_paths = [p for p in cfg.watch_paths if os.path.exists(p)]
    
    if not valid_paths:
        log.error("Nenhum caminho válido encontrado no config.json.")
        return

    # Procurar ficheiros de pilotos e logs em todos os caminhos válidos
    pilot_files = []
    mission_log_path = None
    
    for path in valid_paths:
        pilot_files.extend(glob.glob(os.path.join(path, "Pilot*")))
        potential_log = os.path.join(path, "mission.log")
        if os.path.exists(potential_log):
            mission_log_path = potential_log

    with open(OUTPUT_FILE, "w", encoding="utf-8") as rep:
        rep.write("═" * 60 + "\n")
        rep.write("RELATÓRIO DE EXTRAÇÃO DE DADOS - WoFF BHaH II Watchdog\n")
        rep.write("═" * 60 + "\n\n")
        
        # ─── 1. DOSSIERS E DADOS DE PILOTO ───
        for p_file in pilot_files:
            fname = os.path.basename(p_file).lower()
            
            if "dossier" in fname:
                rep.write(f"📦 FONTE: {fname} (Ficheiro Binário Encriptado)\n")
                rep.write("-" * 60 + "\n")
                parser = WoFFDossierParser()
                if parser.parse(p_file):
                    p = parser.pilot
                    if p:
                        dados = [
                            ("Nome Completo", p.name, "Índices 4, 5"),
                            ("Nação", p.nation, "Mapeamento Dinâmico"),
                            ("Patente", p.rank, "Índice 3"),
                            ("Status RPG", p.status, "Mapeamento Dinâmico"),
                            ("Data de Nascimento", p.birthDate, "Mapeamento Dinâmico"),
                            ("Local de Nascimento", p.birthPlace, "Índice 92"),
                            ("Foto ID", p.photo, "Índice 100"),
                            ("Esquadrão Atual", p.squadron, "Índice 83"),
                            ("Aeronave Atual", p.aircraft, "Índice 84"),
                            ("Minutos de Voo", p.flminutes, "Índice 11"),
                            ("Nº Total de Missões", p.missions, "Índice 46"),
                            ("Vitórias Confirmadas", p.killsCount, "Índice 17"),
                            ("Skill", p.skill, "Índice 41"),
                        ]
                        for nome, valor, origem in dados:
                            rep.write(f"  -> {nome}: {valor if valor else 'Vazio'} (Origem: {origem})\n")
                        
                        if parser.decorations:
                            rep.write("  -> Medalhas:\n")
                            for d in parser.decorations:
                                rep.write(f"     - {d.name}\n")
                                
                        if parser.wingmen:
                            rep.write("  -> Wingmen:\n")
                            for w in parser.wingmen:
                                rep.write(f"     - {w.rank} {w.fName} {w.sName}\n")
                rep.write("\n")
                
            elif "squads" in fname or "log" in fname or "claims" in fname:
                rep.write(f"📦 FONTE: {fname} (Ficheiro Texto Delimitado)\n")
                rep.write("-" * 60 + "\n")
                parser = WoFFPilotDataParser()
                if parser.parse(p_file):
                    if parser.pilot:
                        rep.write(f"  -> Esquadrão: {parser.pilot.squadron}\n")
                        rep.write(f"  -> Base: {parser.pilot.aerodrome}\n")
                    rep.write(f"  -> Missões extraídas: {len(parser.missions)}\n")
                    rep.write(f"  -> Vitórias extraídas: {len(parser.victories)}\n")
                rep.write("\n")

        # ─── 2. MISSION.LOG ───
        if mission_log_path:
            rep.write(f"🛫 FONTE: mission.log (Plano de Voo)\n")
            rep.write("=" * 60 + "\n")
            parser = WoFFMissionLogParser()
            if parser.parse(mission_log_path):
                m = parser.mission
                if m:
                    rep.write(f"  -> Data: {m.date}\n")
                    rep.write(f"  -> Aeronave: {m.aircraft}\n")
                    if parser.pilot:
                        rep.write(f"  -> Esquadrão: {parser.pilot.squadron}\n")
                    rep.write(f"  -> Waypoints Extraídos: {len(parser.flight_plan)}\n")
                    for wp in parser.flight_plan[:3]: # Mostra primeiros 3
                        rep.write(f"     -> {wp['type']} (Lat: {wp['lat']}, Lon: {wp['lon']})\n")
            rep.write("\n")

        rep.write("═" * 60 + "\n")
        rep.write("FIM DO RELATÓRIO\n")

    log.info(f"✅ Relatório gerado com sucesso: {os.path.abspath(OUTPUT_FILE)}")

if __name__ == "__main__":
    main()
