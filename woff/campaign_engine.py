#!/usr/bin/env python3
"""
Motor de Campanha (campaign_engine.py)
══════════════════════════════════════════════════════════════════
"""
import logging
from datetime import datetime
from rpg_system import rpg_system
from narrative_generator import narrative_generator
from database import DatabaseManager

log = logging.getLogger("WoFFWatch")

class CampaignEngine:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def process_mission_end(self, pilot_id: str, mission_id: str):
        log.info(f"[RPG] A processar fim de missão para o piloto {pilot_id}...")
        
        # 1. Buscar dados de forma segura (Piloto, Missão Exata, Histórico)
        pilot_dict, current_mission, m_list = self.db_manager.get_mission_and_history(pilot_id, mission_id)
        
        # FIX: Se a missão não estiver na DB (race condition), abortamos em vez de adivinhar.
        if not pilot_dict or not current_mission:
            log.warning(f"Missão {mission_id} não encontrada na DB para o piloto {pilot_id}. A abortar processamento RPG.")
            return
            
        real_pilot_id = pilot_dict["id"]
        
        # 2. Calcular Stats RPG (Usa o histórico)
        fatigue = rpg_system.calculate_fatigue(m_list)
        morale = rpg_system.calculate_morale(m_list, pilot_dict.get("status", "Active"))
        stress = rpg_system.calculate_stress(m_list)
        
        # 3. Guardar Stats RPG
        self.db_manager.update_pilot_rpg_stats(real_pilot_id, fatigue, morale, stress)
        
        # 4. Gerar Narrativa (Usa os dados da missão EXATA)
        narrative = narrative_generator.generate(pilot_dict["name"], current_mission)
        
        # 5. Guardar Diário (O mission_id agora é garantido que existe na DB)
        self.db_manager.save_diary_entry(
            pilot_id=real_pilot_id, 
            mission_id=mission_id, 
            entry_date=current_mission.get("date", ""), 
            narrative=narrative
        )
        
        log.info(f"  ✓ RPG Atualizado: Fadiga={fatigue} | Moral={morale} | Stress={stress}")

    def process_life_events(self, pilot_name: str, new_status: str, new_rank: str, old_status: str, old_rank: str):
        narrative = narrative_generator.generate_life_event(new_status, old_status, new_rank, old_rank)
        
        if narrative:
            log.info(f"[RPG] Evento de vida detetado para {pilot_name}!")
            
            # FIX: Usar método público dedicado para buscar o ID do piloto
            real_pilot_id = self.db_manager.get_pilot_id_by_name(pilot_name)
            
            if real_pilot_id:
                today = datetime.now().strftime("%Y-%m-%d")
                
                # Guardar entrada de diário (missionId é NULL para eventos de vida)
                self.db_manager.save_diary_entry(
                    pilot_id=real_pilot_id, 
                    mission_id=None, 
                    entry_date=today, 
                    narrative=narrative
                )
                log.info(f"  📝 Diário de Bordo atualizado com Evento de Vida.")