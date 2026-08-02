#!/usr/bin/env python3
"""
Motor de Campanha (campaign_engine.py)
══════════════════════════════════════════════════════════════════
Orquestra a Fase 2 e 3. Lê a Base de Dados, chama o RPGSystem e 
o NarrativeGenerator, e guarda os resultados.
══════════════════════════════════════════════════════════════════
"""
import logging
from typing import List, Optional

from .database import DatabaseManager
from .rpg_system import rpg_system
from .narrative_generator import narrative_generator
from .models import WoFFWingman

log = logging.getLogger("WoFFWatch")

class CampaignEngine:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def process_mission_end(self, pilot_id: str, mission_id: str):
        log.info(f"[RPG] A processar fim de missão para o piloto {pilot_id}...")

        db_result = self.db_manager.get_mission_and_history(pilot_id, mission_id)

        if not db_result or not isinstance(db_result, tuple) or len(db_result) != 3:
            log.error(
                "DatabaseManager.get_mission_and_history retornou um formato inesperado. "
                "Abortando RPG."
            )
            return

        pilot_dict, current_mission, m_list = db_result

        if not pilot_dict or not current_mission:
            log.warning(
                f"Missão {mission_id} não encontrada na DB para o piloto {pilot_id}. "
                "A abortar processamento RPG."
            )
            return

        real_pilot_id = pilot_dict["id"]

        fatigue = rpg_system.calculate_fatigue(m_list)
        morale = rpg_system.calculate_morale(
            m_list, pilot_dict.get("status", "Active")
        )
        stress = rpg_system.calculate_stress(m_list)

        self.db_manager.update_pilot_rpg_stats(real_pilot_id, fatigue, morale, stress)

        narrative = narrative_generator.generate(
            pilot_dict["name"], current_mission
        )

        # FIX: Usar data da missão em vez de datetime.now()
        entry_date = current_mission.get("date", "") or self.db_manager.get_pilot_game_date(real_pilot_id)

        self.db_manager.save_diary_entry(
            pilot_id=real_pilot_id,
            mission_id=mission_id,
            entry_date=entry_date,
            narrative=narrative
        )

        log.info(
            f"  ✓ RPG Atualizado: Fadiga={fatigue} | Moral={morale} | Stress={stress}"
        )

    def process_life_events(
        self, pilot_name: str, new_status: str, new_rank: str,
        old_status: Optional[str], old_rank: Optional[str],
        event_date: Optional[str] = None
    ):
        """Chamado quando o Dossier é atualizado. Verifica mudanças de status/rank."""
        narrative = narrative_generator.generate_life_event(
            new_status, old_status, new_rank, old_rank
        )

        if not narrative:
            return

        log.info(f"[RPG] Evento de vida detetado para {pilot_name}!")

        real_pilot_id = self.db_manager.resolve_pilot_id(pilot_name)
        if not real_pilot_id:
            log.warning(f"Piloto {pilot_name} não resolvido para evento de vida.")
            return

        # FIX: Usar data do jogo se não fornecida
        today = event_date or self.db_manager.get_pilot_game_date(real_pilot_id)

        self.db_manager.save_diary_entry(
            pilot_id=real_pilot_id,
            mission_id=None,
            entry_date=today,
            narrative=narrative
        )
        log.info("  📝 Diário de Bordo atualizado com Evento de Vida.")

    def process_wingmen_changes(
        self, pilot_name: str, new_wingmen: List[WoFFWingman],
        event_date: Optional[str] = None
    ):
        """
        Compara os wingmen recém-extraídos com os guardados na DB.
        Gera entradas de diário para mortes, ferimentos e chegadas.
        """
        log.info(f"[RPG] A verificar mudanças nos wingmen de {pilot_name}...")

        if not new_wingmen:
            log.warning(
                f"  Lista de wingmen vazia para {pilot_name}. "
                "Abortando comparação para evitar falsos positivos."
            )
            return

        real_pilot_id = self.db_manager.resolve_pilot_id(pilot_name)
        if not real_pilot_id:
            log.warning(f"Piloto {pilot_name} não resolvido para verificar wingmen.")
            return

        old_wingmen = self.db_manager.get_wingmen_by_pilot(real_pilot_id)

        old_map = {f"{w['fName']} {w['sName']}": w['status'] for w in old_wingmen}
        new_map = {f"{w.fName} {w.sName}": w.status for w in new_wingmen}

        events = []

        for name, old_status in old_map.items():
            if name in new_map:
                new_status = new_map[name]
                if old_status != new_status:
                    new_s = new_status.lower()
                    if "wound" in new_s or "hospital" in new_s:
                        events.append(("wounded", name))
                    elif "kia" in new_s or "dead" in new_s:
                        events.append(("kia", name))
            else:
                events.append(("missing", name))

        for name in new_map.keys():
            if name not in old_map:
                events.append(("new", name))

        # FIX: Usar data do jogo se não fornecida
        today = event_date or self.db_manager.get_pilot_game_date(real_pilot_id)

        for event_type, name in events:
            narrative = narrative_generator.generate_wingman_event(name, event_type)
            if narrative:
                self.db_manager.save_diary_entry(
                    real_pilot_id, None, today, narrative
                )
                log.info(
                    f"  📝 Evento de Wingman registado: {name} ({event_type})"
                )