import unittest
import tempfile
import os
import sqlite3
import gc
from typing import Any
from unittest.mock import patch


from ..database import DatabaseManager
from ..campaign_engine import CampaignEngine
from ..models import WoFFPilot, WoFFMission

class TestCampaignEngine(unittest.TestCase):
    # Anotações de tipo ao nível da classe
    db: DatabaseManager
    engine: CampaignEngine
    tmp_db: Any
    
    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        self.db = DatabaseManager(self.tmp_db.name)
        self.engine = CampaignEngine(self.db)
    
    def tearDown(self):
        # FIX: Ignorar o erro de tipo ao atribuir None, pois é intencional para o GC
        self.engine = None  # type: ignore[assignment]
        self.db = None      # type: ignore[assignment]
        gc.collect()
        
        for ext in ["", "-wal", "-shm"]:
            path = self.tmp_db.name + ext
            if os.path.exists(path):
                try:
                    os.unlink(path)
                except PermissionError:
                    pass
    
    def test_process_mission_end_race_condition_mocked(self):
        """
        Testa a Race Condition de forma determinística.
        """
        pilot = WoFFPilot(name="Race Pilot")
        self.db.merge_and_write(pilot, [], [], [])
        
        with patch.object(self.db, 'get_mission_and_history', return_value=(None, None, [])):
            result = self.engine.process_mission_end(pilot.name, "M_RACE")
        
        self.assertIsNone(result)
        
        conn = sqlite3.connect(self.tmp_db.name)
        cursor = conn.execute("SELECT COUNT(*) FROM diary_entries")
        self.assertEqual(cursor.fetchone()[0], 0)
        
        cursor = conn.execute("SELECT COUNT(*) FROM pilot_rpg_stats")
        self.assertEqual(cursor.fetchone()[0], 0)
        conn.close()
    
    def test_process_mission_end_success(self):
        """Testa processamento completo de missão (RPG Stats e Diário)."""
        pilot = WoFFPilot(name="Test Pilot")
        mission = WoFFMission(id="M001", pilotId=pilot.id, date="1917-04-06", time="10:30", missionType="OP")
        self.db.merge_and_write(pilot, [mission], [], [])
        
        self.engine.process_mission_end(pilot.name, "M001")
        
        conn = sqlite3.connect(self.tmp_db.name)
        
        cursor = conn.execute("SELECT * FROM pilot_rpg_stats WHERE pilotId = ?", (pilot.id,))
        self.assertIsNotNone(cursor.fetchone())
        
        cursor = conn.execute("SELECT * FROM diary_entries WHERE missionId = ?", ("M001",))
        diary_row = cursor.fetchone()
        self.assertIsNotNone(diary_row)
        self.assertIn("1917-04-06", diary_row[4]) 
        
        conn.close()
    
    def test_process_life_events_promotion(self):
        """Testa deteção de promoção e geração de entrada de diário."""
        pilot = WoFFPilot(name="Promo Pilot", rank="Lieutenant", status="Active")
        self.db.merge_and_write(pilot, [], [], [])
        
        self.engine.process_life_events(
            "Promo Pilot", "Active", "Captain", "Active", "Lieutenant"
        )
        
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
