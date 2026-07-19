#!/usr/bin/env python3
"""
Gerador de Narrativas (narrative_generator.py)
══════════════════════════════════════════════════════════════════
Gera entradas de Diário de Bordo imersivas baseadas nos dados 
extraídos das missões do WoFF BHaH II.
══════════════════════════════════════════════════════════════════
"""
import random
import logging

log = logging.getLogger("WoFFWatch")

class NarrativeGenerator:
    def __init__(self):
        self.templates = [
            "{date} - O céu de Flandres.\nHoje voámos numa {mission_type} no meu {aircraft}. {action} {result}",
            "{date} - Diário de Bordo.\nMissão de {mission_type}. Decolámos de {aerodrome} com o tempo {weather}. {action} {result}",
            "{date}\nMais um dia nesta guerra. A tarefa de hoje era uma {mission_type}. {action} {result}"
        ]
        
        self.actions = [
            "Patrolhámos a área designada",
            "Aproximámo-nos das linhas inimigas",
            "A nossa esquadrilha formou e rumamos ao setor",
            "O voo decorreu com normalidade até ao objetivo"
        ]
        
        self.results_success = [
            "Regressei à base são e salvo. Mais um dia para contar.",
            "A aterragem foi suave. Mais uma missão cumprida.",
            "O avião está em boas condições. Sinto-me com sorte."
        ]
        
        self.results_damaged = [
            "O meu avião foi atingido, mas consegui trazer a máquina de volta à base.",
            "Apanhei fogo inimigo. O avião está danificado, mas eu estou vivo.",
            "Tive de fazer uma aterragem apressada. O avião vai precisar de reparação."
        ]
        
        self.results_wounded = [
            "Fui ferido durante o voo. A dor é grande, mas sobrevivi.",
            "Apanhei um fragmento de shrapnel. Estou a caminho do hospital.",
            "O médico diz que tive sorte. O avião está destruído, mas eu vou recuperar."
        ]
        
        self.results_forced_landing = [
            "Tive de fazer uma aterragem forçada atrás das linhas inimigas. Não sei o que vai acontecer.",
            "O motor morreu e fui abaixo. Aterrei em terreno hostil.",
            "Fui abatido. Consegui aterrar, mas estou perdido."
        ]

    def generate(self, pilot_name: str, mission_data: dict) -> str:
        """
        Gera uma narrativa baseada nos dados da missão.
        mission_data: dicionário com chaves como date, missionType, aircraft, etc.
        """
        date = mission_data.get("date", "Data desconhecida")
        mission_type = mission_data.get("missionType", "patrulha")
        aircraft = mission_data.get("aircraft", "aeronave desconhecida")
        aerodrome = mission_data.get("aerodrome", "base aérea")
        weather = mission_data.get("weather", "instável")
        
        # Escolher uma ação e um resultado ao acaso (para dar variedade)
        action = random.choice(self.actions)
        
        # Determinar o resultado baseado no estado da missão
        result_text = random.choice(self.results_success) # Padrão: sucesso
        
        if mission_data.get("woundsReceived", 0) > 0:
            result_text = random.choice(self.results_wounded)
        elif mission_data.get("damageReceived", 0) > 0:
            result_text = random.choice(self.results_damaged)
        elif "force" in mission_data.get("result", "").lower() or "crash" in mission_data.get("result", "").lower():
            result_text = random.choice(self.results_forced_landing)
            
        # Adicionar menção a vitórias, se houver
        claims = mission_data.get("claimsCount", "0")
        if claims != "0":
            result_text += f" Tive a honra de abater {claims} aeronave(ns) inimiga(s) hoje!"
            
        # Escolher um template e preencher
        template = random.choice(self.templates)
        narrative = template.format(
            date=date,
            mission_type=mission_type,
            aircraft=aircraft,
            action=action,
            result=result_text,
            aerodrome=aerodrome,
            weather=weather
        )
        
        return narrative

# Instância global
narrative_generator = NarrativeGenerator()