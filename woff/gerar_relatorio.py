#!/usr/bin/env python3
"""
Gerador de Relatório de Extração de Dados (Multi-Piloto)
══════════════════════════════════════════════════════════════════
Lê todos os perfis de piloto criados pelo utilizador, extrai todas 
as informações possíveis e gera um ficheiro woff_data_report.txt 
mapeando a origem de cada dado.
══════════════════════════════════════════════════════════════════
"""
import os
import sys
import glob
import logging

# Adicionar a pasta woff ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "woff"))

from parsers.dossier_parser import WoFFDossierParser
from parsers.pilot_data_parser import WoFFPilotDataParser
from parsers.mission_log_parser import WoFFMissionLogParser

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("ReportGen")

# Caminhos base do seu jogo
BASE_PILOTS = r"A:\OBDSoftware\WOFF\OBDWW1 Over Flanders Fields\campaigns\CampaignData\Pilots"
MISSION_LOG = r"A:\OBDSoftware\WOFF\Logs\mission.log"

OUTPUT_FILE = "woff_data_report.txt"

def main():
    log.info("A iniciar geração de relatório...")
    
    # Procurar todos os ficheiros Dossier na pasta
    dossiers = glob.glob(os.path.join(BASE_PILOTS, "Pilot*Dossier.txt"))
    
    if not dossiers:
        log.error("Nenhum piloto encontrado na pasta.")
        return

    with open(OUTPUT_FILE, "w", encoding="utf-8") as rep:
        rep.write("═" * 60 + "\n")
        rep.write("RELATÓRIO DE EXTRAÇÃO DE DADOS - WoFF BHaH II Watchdog\n")
        rep.write(f"Total de Pilotos Encontrados: {len(dossiers)}\n")
        rep.write("═" * 60 + "\n\n")
        
        for f_dossier in dossiers:
            # Extrai o ID do piloto do nome do ficheiro (ex: Pilot1)
            base_name = os.path.basename(f_dossier).replace("Dossier.txt", "")
            log.info(f"Processando {base_name}...")
            
            # Instanciar parsers para cada piloto
            dossier_parser = WoFFDossierParser()
            pilot_parser = WoFFPilotDataParser()
            
            f_squads = os.path.join(BASE_PILOTS, f"{base_name}Squads.txt")
            f_log = os.path.join(BASE_PILOTS, f"{base_name}Log.txt")
            f_claims = os.path.join(BASE_PILOTS, f"{base_name}Claims.txt")

            rep.write(f"🧑‍✈️ PERFIL: {base_name}\n")
            rep.write("=" * 60 + "\n")
            
            # ─── 1. DOSSIER BINÁRIO ───
            rep.write("📦 FONTE 1: Dossier.txt (Ficheiro Binário Encriptado)\n")
            rep.write("-" * 60 + "\n")
            if os.path.exists(f_dossier) and dossier_parser.parse(f_dossier):
                p = dossier_parser.pilot
                if p:
                    dados_dossier = [
                        ("Nome Completo", p.name, "Índices 4, 5"),
                        ("Nação", p.nation, "Mapeamento Dinâmico"),
                        ("Patente", p.rank, "Índice 3"),
                        ("Status RPG", p.status, "Mapeamento Dinâmico"),
                        ("Data de Nascimento", p.birthDate, "Mapeamento Dinâmico"),
                        ("Local de Nascimento", p.birthPlace, "Índice 92"),
                        ("Data de Alistamento", p.enlisted, "Índices 12, 13, 14"),
                        ("Data Início Campanha", p.startDate, "Índices 6, 7, 8"),
                        ("Minutos de Voo Totais", p.flminutes, "Índice 11"),
                        ("Nº Total de Missões", p.missions, "Índice 46"),
                        ("Reivindicações (Claims)", p.claimsCount, "Índice 16"),
                        ("Vitórias Confirmadas", p.killsCount, "Índice 17"),
                        ("Skill (Habilidade)", p.skill, "Índice 41"),
                        ("Reputação", p.reputation, "Índice 52"),
                        ("Esquadrão Atual", p.squadron, "Índice 83"),
                        ("Aeronave Atual", p.aircraft, "Índice 84"),
                        ("Aeródromo Atual", p.aerodrome, "Índice 88"),
                        ("Setor/Região", p.sector, "Índice 89"),
                        ("Biografia Narrativa", p.notes, "Mapeamento Dinâmico"),
                    ]
                    
                    for nome, valor, origem in dados_dossier:
                        rep.write(f"  -> {nome}:\n")
                        rep.write(f"     Valor : {valor if valor else 'Vazio'}\n")
                        rep.write(f"     Origem: {origem} (Decifrado XOR)\n\n")
                    
                    # Listar TODOS os Membros do Esquadrão (AI)
                    rep.write("  -> Membros do Esquadrão (AI) e suas estatísticas:\n")
                    rep.write("     Origem: Strings anexadas no Dossier\n")
                    for s in dossier_parser.raw_strings:
                        # Filtra strings que têm o padrão de piloto AI (contém ';' e patentes)
                        if ";" in s and len(s) > 20 and any(rank in s for rank in ["Lieutenant", "Capitaine", "Caporal", "Sergent", "Sous", "Major", "Colonel"]):
                            rep.write(f"     - {s}\n")
                    rep.write("\n")
            else:
                rep.write("  [ERRO] Dossier não encontrado ou falha ao decifrar.\n\n")

            # ─── 2. SQUADS.TXT ───
            rep.write("📦 FONTE 2: Squads.txt (Histórico de Transferências)\n")
            rep.write("-" * 60 + "\n")
            if os.path.exists(f_squads) and pilot_parser.parse(f_squads):
                p = pilot_parser.pilot
                rep.write(f"  -> Última Transferência:\n")
                rep.write(f"     Esquadrão : {p.squadron} (Origem: Coluna 7)\n")
                rep.write(f"     Aeronave  : {p.aircraft} (Origem: Coluna 8)\n")
                rep.write(f"     Base      : {p.aerodrome} (Origem: Coluna 6)\n")
                rep.write(f"     Setor     : {p.sector} (Origem: Coluna 5)\n")
                rep.write(f"     Patente   : {p.rank} (Origem: Regex na Coluna 10)\n\n")
            else:
                rep.write("  [AVISO] Squads.txt não encontrado para este piloto.\n\n")

            # ─── 3. LOG.TXT ───
            rep.write("📦 FONTE 3: Log.txt (Histórico de Missões)\n")
            rep.write("-" * 60 + "\n")
            if os.path.exists(f_log) and pilot_parser.parse(f_log):
                rep.write(f"  -> Total de Missões Extraídas: {len(pilot_parser.missions)}\n")
                if pilot_parser.missions:
                    m = pilot_parser.missions[0] # Mostra a primeira missão como exemplo
                    rep.write(f"  -> Exemplo (Primeira Missão):\n")
                    rep.write(f"     Data       : {m.date} (Origem: Colunas 0, 1, 2)\n")
                    rep.write(f"     Setor      : {m.sector} (Origem: Coluna 5)\n")
                    rep.write(f"     Aeródromo  : {m.aerodrome} (Origem: Coluna 6)\n")
                    rep.write(f"     Tipo       : {m.missionType} (Origem: Coluna 7)\n")
                    rep.write(f"     Aeronave   : {m.aircraft} (Origem: Coluna 8)\n")
                    rep.write(f"     Duração    : {m.duration} (Origem: Coluna 10)\n")
                    rep.write(f"     Esquadrão  : {m.squadron} (Origem: Coluna 13)\n")
                    rep.write(f"     Narrativa  : {m.notes[:80]}... (Origem: Coluna 19)\n")
                    rep.write(f"     Resultado  : {m.result} (Origem: Heurística na Narrativa)\n\n")
            else:
                rep.write("  [AVISO] Log.txt não encontrado ou sem missões.\n\n")

            # ─── 4. CLAIMS.TXT ───
            rep.write("📦 FONTE 4: Claims.txt (Vitórias e Abates)\n")
            rep.write("-" * 60 + "\n")
            if os.path.exists(f_claims) and pilot_parser.parse(f_claims):
                rep.write(f"  -> Total de Vitórias Extraídas: {len(pilot_parser.victories)}\n")
                if pilot_parser.victories:
                    v = pilot_parser.victories[0] # Mostra a primeira vitória
                    rep.write(f"  -> Exemplo (Primeira Vitória):\n")
                    rep.write(f"     Data       : {v.date} (Origem: Colunas 0, 1, 2)\n")
                    rep.write(f"     Hora       : {v.time} (Origem: Colunas 3, 4)\n")
                    rep.write(f"     Setor      : {v.sector} (Origem: Coluna 5)\n")
                    rep.write(f"     Aeronave   : {v.aircraft} (Origem: Coluna 8)\n")
                    rep.write(f"     Inimigo    : {v.enemyType} (Origem: Coluna 10)\n")
                    rep.write(f"     Tipo Vitór.: {v.victoryType} (Origem: Coluna 11)\n")
                    rep.write(f"     Confirmada : {v.confirmed} (Origem: Heurística na Coluna 11)\n\n")
            else:
                rep.write("  [AVISO] Claims.txt não encontrado ou sem vitórias.\n\n")

            rep.write("\n")

        # ─── 5. MISSION.LOG (Apenas no final, pois é global) ───
        rep.write("🛫 FONTE 5: mission.log (Plano de Voo da Última Missão Jogada)\n")
        rep.write("=" * 60 + "\n")
        mission_parser = WoFFMissionLogParser()
        if os.path.exists(MISSION_LOG) and mission_parser.parse(MISSION_LOG):
            m = mission_parser.mission
            rep.write(f"  -> Briefing: {mission_parser.briefing[:100]}...\n")
            rep.write(f"     Origem: Tag <Overview> no XML do Log\n\n")
            rep.write(f"  -> Dados da Missão:\n")
            rep.write(f"     Data       : {m.date} (Origem: Atributo Date na tag <Params>)\n")
            rep.write(f"     Clima      : {m.weather} (Origem: Atributo Weather na tag <Params>)\n")
            rep.write(f"     Aeronave   : {m.aircraft} (Origem: Atributo Type na tag <Unit IsPlayer='y'>)\n")
            rep.write(f"     Esquadrão  : {mission_parser.pilot.squadron} (Origem: Atributo SquadName na tag <AirFormation>)\n")
            rep.write(f"  -> Membros da Formação Voadora (Flight):\n")
            rep.write(f"     Origem: Tags <Unit> dentro da formação do jogador\n")
            for member in mission_parser.squad_members:
                rep.write(f"     - {member}\n")
            rep.write(f"  -> Debriefing do Motor: {mission_parser.debriefing}\n")
            rep.write(f"     Origem: Análise de texto pós-bloco XML\n\n")
        else:
            rep.write("  [AVISO] mission.log não encontrado.\n\n")

        rep.write("═" * 60 + "\n")
        rep.write("FIM DO RELATÓRIO\n")

    log.info(f"✅ Relatório gerado com sucesso: {os.path.abspath(OUTPUT_FILE)}")

if __name__ == "__main__":
    main()