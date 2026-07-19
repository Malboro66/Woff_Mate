#!/usr/bin/env python3
"""
Motor de Campanha (campaign_engine.py)
══════════════════════════════════════════════════════════════════
Orquestra a Fase 2. Lê a Base de Dados, chama o RPGSystem e 
o NarrativeGenerator, e guarda os resultados.
══════════════════════════════════════════════════════════════════
"""
import sqlite3
import uuid
import logging
from rpg_system import rpg_system
from narrative_generator import narrative_generator

log = logging.getLogger("WoFFWatch")

class CampaignEngine:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def process_mission_end(self, pilot_id: str, mission_id: str):
        """
        Chamado pelo handler.py quando uma missão nova é guardada na DB.
        Calcula o RPG e gera o diário.
        """
        log.info(f"[RPG] A processar fim de missão para o piloto {pilot_id}...")
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            # 1. Buscar o piloto e o seu estado atual
            pilot = conn.execute("SELECT * FROM pilots WHERE id = ? OR name = ?", (pilot_id, pilot_id)).fetchone()
            if not pilot:
                log.warning(f"Piloto {pilot_id} não encontrado na DB para processar RPG.")
                return
                
            real_pilot_id = pilot["id"]
                
            # 2. Buscar as últimas 10 missões para calcular tendências
            missions = conn.execute(
                "SELECT * FROM missions WHERE pilotId = ? ORDER BY date DESC LIMIT 10", 
                (real_pilot_id,)
            ).fetchall()
            
            if not missions:
                return
                
            # Converter linhas de DB para dicionários para o RPGSystem
            m_list = [dict(m) for m in missions]
            latest_mission = m_list[0]
            
            # 3. Calcular Stats RPG
            fatigue = rpg_system.calculate_fatigue(m_list)
            morale = rpg_system.calculate_morale(m_list, pilot["status"])
            stress = rpg_system.calculate_stress(m_list)
            
            # 4. Guardar Stats RPG na DB
            conn.execute("""
                INSERT INTO pilot_rpg_stats (pilotId, fatigue, morale, stress, last_updated)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(pilotId) DO UPDATE SET 
                    fatigue=excluded.fatigue, 
                    morale=excluded.morale, 
                    stress=excluded.stress, 
                    last_updated=excluded.last_updated
            """, (real_pilot_id, fatigue, morale, stress))
            
            # 5. Gerar e guardar Narrativa (Diário)
            # Usamos o nome do piloto e os dados da última missão
            narrative = narrative_generator.generate(pilot["name"], latest_mission)
            
            # Verificar se já existe um diário para esta missão
            existing_diary = conn.execute(
                "SELECT id FROM diary_entries WHERE pilotId = ? AND missionId = ?", 
                (real_pilot_id, mission_id)
            ).fetchone()
            
            if not existing_diary:
                diary_id = uuid.uuid4().hex[:12]
                conn.execute("""
                    INSERT INTO diary_entries (id, pilotId, missionId, entry_date, narrative)
                    VALUES (?, ?, ?, ?, ?)
                """, (diary_id, real_pilot_id, mission_id, latest_mission.get("date", ""), narrative))
                log.info(f"  📝 Diário de Bordo gerado para a missão de {latest_mission.get('date')}.")
            else:
                log.debug("Diário de bordo já existia para esta missão. Ignorado.")
            
            conn.commit()
            log.info(f"  ✓ RPG Atualizado: Fadiga={fatigue} | Moral={morale} | Stress={stress}")
            
        except Exception as e:
            log.error(f"Erro no CampaignEngine: {e}")
        finally:
            conn.close()