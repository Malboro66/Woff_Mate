import unittest
import tempfile
import os
import sqlite3
import sys

# Adicionar a pasta woff ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import DatabaseManager
from campaign_engine import CampaignEngine
from models import WoFFPilot, WoFFMission

class TestCampaignEngine(unittest.TestCase):
    
    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        self.db = DatabaseManager(self.tmp_db.name)
        self.engine = CampaignEngine(self.db)
    
    def tearDown(self):
        self.db = None
        self.engine = None
        if os.path.exists(self.tmp_db.name):
            os.unlink(self.tmp_db.name)
    
    def test_process_mission_end_race_condition(self):
        """Testa comportamento quando a missão ainda não existe na DB (Race Condition)."""
        # 1. Inserir o piloto, mas NÃO a missão
        pilot = WoFFPilot(name="Test Pilot")
        self.db.merge_and_write(pilot, [], [], [])
        
        # 2. Chamar process_mission_end com um ID de missão inexistente
        result = self.engine.process_mission_end(pilot.name, "MISSING_ID")
        
        # 3. Deve retornar None (abortou) sem crashar
        self.assertIsNone(result)
        
        # 4. Garantir que não foi inserido nenhum diário nem stats de RPG
        conn = sqlite3.connect(self.tmp_db.name)
        cursor = conn.execute("SELECT COUNT(*) FROM diary_entries")
        self.assertEqual(cursor.fetchone()[0], 0)
        
        cursor = conn.execute("SELECT COUNT(*) FROM pilot_rpg_stats")
        self.assertEqual(cursor.fetchone()[0], 0)
        conn.close()
    
    def test_process_mission_end_success(self):
        """Testa processamento completo de missão (RPG Stats e Diário)."""
        # 1. Inserir piloto e missão
        pilot = WoFFPilot(name="Test Pilot")
        mission = WoFFMission(id="M001", pilotId=pilot.id, date="1917-04-06", time="10:30", missionType="OP")
        self.db.merge_and_write(pilot, [mission], [], [])
        
        # 2. Processar
        self.engine.process_mission_end(pilot.name, "M001")
        
        # 3. Verificar RPG stats e diário (usando ligação direta para validar)
        conn = sqlite3.connect(self.tmp_db.name)
        
        cursor = conn.execute("SELECT * FROM pilot_rpg_stats WHERE pilotId = ?", (pilot.id,))
        self.assertIsNotNone(cursor.fetchone())
        
        cursor = conn.execute("SELECT * FROM diary_entries WHERE missionId = ?", ("M001",))
        diary_row = cursor.fetchone()
        self.assertIsNotNone(diary_row)
        # O texto gerado pelo NarrativeGenerator deve mencionar o tipo de missão ou data
        self.assertIn("1917-04-06", diary_row[4]) 
        
        conn.close()
    
    def test_process_life_events_promotion(self):
        """Testa deteção de promoção e geração de entrada de diário."""
        # 1. Inserir piloto com rank antigo
        pilot = WoFFPilot(name="Promo Pilot", rank="Lieutenant", status="Active")
        self.db.merge_and_write(pilot, [], [], [])
        
        # 2. Simular promoção (Status mantém-se, Rank muda)
        self.engine.process_life_events(
            "Promo Pilot", "Active", "Captain", "Active", "Lieutenant"
        )
        
        # 3. Verificar se a entrada de diário foi criada com a narrativa correta
        conn = sqlite3.connect(self.tmp_db.name)
        cursor = conn.execute("SELECT narrative FROM diary_entries WHERE pilotId = ?", (pilot.id,))
        row = cursor.fetchone()
        
        self.assertIsNotNone(row)
        narrative = row[0].lower()
        self.assertIn("promovido", narrative)
        self.assertIn("captain", narrative)
        
        conn.close()

if __name__ == "__main__":
    unittest.main()