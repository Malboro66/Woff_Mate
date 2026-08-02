#!/usr/bin/env python3
"""
Sistema de RPG (rpg_system.py)
══════════════════════════════════════════════════════════════════
Contém as regras de cálculo para o estado RPG do piloto e a geração 
de personalidades únicas para os Wingmen (Sistema 3P).
══════════════════════════════════════════════════════════════════
"""
from datetime import datetime
from typing import List, Dict, Any
import random

class RPGSystem:
    def __init__(self):
        self.MAX_FATIGUE = 100
        self.MAX_MORALE = 100
        self.MAX_STRESS = 100

    def calculate_fatigue(self, missions: List[Dict[str, Any]]) -> int:
        """Calcula a fadiga atual (0-100) com base no histórico recente."""
        if not missions:
            return 0
        
        fatigue = 0
        
        # HACK ELEGANTE: O formato ISO 8601 (YYYY-MM-DD) permite comparação 
        # lexicográfica direta. A função max() encontra a data mais recente 
        # sem necessidade de fazer parse de datas em cada iteração, o que é muito mais rápido.
        today_str = max((str(m.get("date", "")) for m in missions), default="")
        if not today_str:
            return 0
            
        try:
            today = datetime.strptime(today_str, "%Y-%m-%d")
        except Exception:
            return 0

        for m in missions:
            try:
                m_date_str = str(m.get("date", ""))
                if not m_date_str: continue
                m_date = datetime.strptime(m_date_str, "%Y-%m-%d")
                days_ago = (today - m_date).days
                
                if 0 <= days_ago <= 3:
                    is_wounded = m.get("woundsReceived", False)
                    fatigue += 25 if is_wounded else 15
                    if m.get("damageReceived", False):
                        fatigue += 5
            except Exception:
                continue

        # Variável Estocástica: Eventos Raros
        # Ex: "Adrenalina do Combate" reduz a perceived fatigue, ou "Insónia" aumenta.
        event_roll = random.random()
        if event_roll < 0.1:  # 10% de chance de evento aleatório
            if event_roll < 0.05:
                fatigue -= 10  # Sorte, descansou bem apesar de tudo
            else:
                fatigue += 15  # Azar, insónias ou stress extra
                
        return max(0, min(fatigue, self.MAX_FATIGUE))

    def calculate_morale(self, missions: List[Dict[str, Any]], pilot_status: str) -> int:
        """Calcula a moral (0-100) com base em vitórias e baixas recentes.

        Pré-condição: ``missions`` deve estar ordenada da mais recente para a
        mais antiga. Apenas as 10 missões mais recentes são consideradas.
        """
        morale = 75
        
        for m in missions[:10]:
            if m.get("claimsCount", 0) not in (0, "0", ""):
                morale += 5
            if m.get("woundsReceived", False):
                morale -= 10
            elif m.get("damageReceived", False):
                morale -= 3
                
        if pilot_status.lower() in ["wounded", "hospital", "leave", "invalided"]:
            morale -= 20
            
        # Variável Estocástica: Notícias de casa, clima de humor na esquadrilha
        event_roll = random.random()
        if event_roll < 0.15:  # 15% de chance de flutuação de humor
            morale += random.randint(-10, 10)
            
        return max(0, min(morale, self.MAX_MORALE))

    def calculate_stress(self, missions: List[Dict[str, Any]]) -> int:
        """Calcula o stress de combate (0-100).

        Pré-condição: ``missions`` deve estar ordenada da mais recente para a
        mais antiga. Apenas as 5 missões mais recentes são consideradas.
        """
        stress = 0
        
        for m in missions[:5]:
            try:
                contacts = int(m.get("enemyContacts", 0) or 0)
                stress += contacts * 4
                
                result = str(m.get("result", "")).lower()
                if "force" in result or "crash" in result:
                    stress += 20
            except Exception:
                continue

        # Variável Estocástica: Traumas persistentes ou alívio
        event_roll = random.random()
        if event_roll < 0.1:  # 10% de chance de flashback traumático
            stress += 15
            
        return min(stress, self.MAX_STRESS)

    def generate_personality(self) -> Dict[str, Any]:
        """Gera uma personalidade única para um Wingman AI baseada no modelo 3P."""
        attributes = {
            "aerial_skill": random.randint(20, 95),
            "aggression": random.randint(10, 90),
            "charisma": random.randint(10, 90),
            "intelligence": random.randint(20, 95),
            "physicality": random.randint(30, 95),
            "professionalism": random.randint(15, 95)
        }
        
        traits = []
        if attributes["aggression"] > 75: traits.append("Reckless")
        elif attributes["aggression"] < 25: traits.append("Cautious")
        if attributes["professionalism"] > 80: traits.append("Disciplined")
        elif attributes["professionalism"] < 30: traits.append("Rogue")
        if attributes["charisma"] > 80: traits.append("Inspiring")
        if attributes["intelligence"] > 80: traits.append("Analytical")
        
        trait = random.choice(traits) if traits else "Standard"
        
        return {
            **attributes,
            "personality_trait": trait
        }

# Instância global para usar no projeto
rpg_system = RPGSystem()