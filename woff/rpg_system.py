#!/usr/bin/env python3
"""
Sistema de RPG (rpg_system.py)
══════════════════════════════════════════════════════════════════
Contém as regras de cálculo para o estado RPG do piloto.
Calcula Fadiga, Moral, Stress e Progressão de Skill baseando-se
no histórico de missões extraídas do jogo.
══════════════════════════════════════════════════════════════════
"""
from datetime import datetime, timedelta
from typing import List, Dict

class RPGSystem:
    def __init__(self):
        # Limites máximos e mínimos
        self.MAX_FATIGUE = 100
        self.MAX_MORALE = 100
        self.MAX_STRESS = 100

    def calculate_fatigue(self, missions: List[Dict]) -> int:
        """
        Calcula a fadiga atual (0-100).
        Regra: +20 por missão nos últimos 3 dias. -10 por dia de descanso.
        """
        if not missions:
            return 0
        
        fatigue = 0
        today_str = missions[-1].get("date")
        try:
            today = datetime.strptime(today_str, "%Y-%m-%d")
        except:
            return 0

        for m in missions:
            try:
                m_date = datetime.strptime(m.get("date", ""), "%Y-%m-%d")
                days_ago = (today - m_date).days
                
                # Missões nos últimos 3 dias causam fadiga
                if 0 <= days_ago <= 3:
                    # Se foi ferido, a fadiga é maior
                    is_wounded = m.get("woundsReceived", False)
                    fatigue += 25 if is_wounded else 15
                    
                    # Se a aeronave foi danificada, soma um pouco
                    if m.get("damageReceived", False):
                        fatigue += 5
            except:
                continue
                
        return min(fatigue, self.MAX_FATIGUE)

    def calculate_morale(self, missions: List[Dict], pilot_status: str) -> int:
        """
        Calcula a moral (0-100). 100 é o máximo.
        Regra: Começa em 75. Vitórias aumentam, mortes/baixas diminuem.
        """
        morale = 75
        
        for m in missions[-10:]: # Olha para as últimas 10 missões
            # Vitórias aumentam a moral
            if m.get("claimsCount", "0") != "0":
                morale += 5
                
            # Ser ferido ou ter o avião muito danificado baixa a moral
            if m.get("woundsReceived", False):
                morale -= 10
            elif m.get("damageReceived", False):
                morale -= 3
                
        # Se o piloto está atualmente ferido ou em licença
        if pilot_status.lower() in ["wounded", "hospital", "leave", "invalided"]:
            morale -= 20
            
        # Manter entre 0 e 100
        return max(0, min(morale, self.MAX_MORALE))

    def calculate_stress(self, missions: List[Dict]) -> int:
        """
        Calcula o stress de combate (0-100).
        Regra: Baseado no número de contactos inimigos recentes e tempo de voo.
        """
        stress = 0
        for m in missions[-5:]: # Últimas 5 missões
            try:
                contacts = int(m.get("enemyContacts", "0"))
                stress += contacts * 4
                
                # Se a missão resultou em aterragem forçada ou KIA
                result = m.get("result", "").lower()
                if "force" in result or "crash" in result:
                    stress += 20
            except:
                continue
                
        return min(stress, self.MAX_STRESS)

# Instância global para usar no projeto
rpg_system = RPGSystem()