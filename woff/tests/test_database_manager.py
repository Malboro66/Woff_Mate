import unittest
import tempfile
import os
import sqlite3
import sys
import gc
from typing import Any

# Adicionar a pasta woff ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import DatabaseManager
from models import WoFFPilot, WoFFMission

class TestDatabaseManager(unittest.TestCase):
    
    # Anotações de tipo para o Pyright
    db: DatabaseManager
    tmp_db: Any
    
    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        self.db = DatabaseManager(self.tmp_db.name)
    
    def tearDown(self):
        # Forçar garbage collection para libertar os locks do SQLite no Windows
        self.db = None  # type: ignore[assignment]
        gc.collect()
        
        for ext in ["", "-wal", "-shm"]:
            path = self.tmp_db.name + ext
            if os.path.exists(path):
                try:
                    os.unlink(path)
                except PermissionError:
                    pass
    
    def test_merge_new_pilot(self):
        """Insere piloto novo e verifica o estado padrão (Active)."""
        pilot = WoFFPilot(name="John Doe", squadron="No. 56 Sqn")
        ok = self.db.merge_and_write(pilot, [], [], [])
        self.assertTrue(ok)
        
        status, rank = self.db.get_pilot_state("John Doe")
        self.assertIsNotNone(status)
        self.assertEqual(status, "Active")
    
    def test_merge_existing_pilot_by_name(self):
        """Atualiza piloto existente pelo nome, garantindo que o COALESCE preserva dados antigos."""
        p1 = WoFFPilot(name="John Doe", squadron="No. 56 Sqn", rank="2nd Lieutenant")
        self.db.merge_and_write(p1, [], [], [])
        
        p2 = WoFFPilot(name="John Doe", squadron="No. 60 Sqn")
        self.db.merge_and_write(p2, [], [], [])
        
        pilot_dict, _, _ = self.db.get_mission_and_history("John Doe", "")
        
        self.assertIsNotNone(pilot_dict)
        assert pilot_dict is not None 
        
        self.assertEqual(pilot_dict["squadron"], "No. 60 Sqn")
        self.assertEqual(pilot_dict["rank"], "2nd Lieutenant")
    
    def test_merge_pilot_by_source_file_glob(self):
        """Testa fallback GLOB para resolver "Pilot 1" -> "Pilot1Dossier.txt"."""
        real = WoFFPilot(name="James Hartley", source_file="Pilot1Dossier.txt")
        self.db.merge_and_write(real, [], [], [])
        
        generic = WoFFPilot(name="Pilot 1", squadron="No. 56 Sqn", source_file="Pilot1Log.txt")
        self.db.merge_and_write(generic, [], [], [])
        
        pilot_dict, _, _ = self.db.get_mission_and_history("James Hartley", "")
        
        self.assertIsNotNone(pilot_dict)
        assert pilot_dict is not None
        
        self.assertEqual(pilot_dict["squadron"], "No. 56 Sqn")
        
        ghost, _, _ = self.db.get_mission_and_history("Pilot 1", "")
        self.assertIsNone(ghost)
    
    def test_mission_foreign_key_constraint(self):
        """Testa que missão com pilotId inválido é rejeitada pela DB."""
        mission = WoFFMission(pilotId="INVALID_ID", date="1917-04-06")
        ok = self.db.merge_and_write(None, [mission], [], [])
        
        # FIX: FOREIGN KEY constraints NÃO são silenciadas por INSERT OR IGNORE.
        # A transação falha com IntegrityError e merge_and_write retorna False.
        self.assertFalse(ok)
        
        conn = sqlite3.connect(self.tmp_db.name)
        cursor = conn.execute("SELECT COUNT(*) FROM missions WHERE pilotId = ?", ("INVALID_ID",))
        self.assertEqual(cursor.fetchone()[0], 0)
        conn.close()
    
    def test_rpg_stats_update(self):
        """Testa UPSERT de stats RPG."""
        pilot = WoFFPilot(name="Test Pilot")
        self.db.merge_and_write(pilot, [], [], [])
        
        self.db.update_pilot_rpg_stats(pilot.id, 50, 80, 30)
        
        conn = sqlite3.connect(self.tmp_db.name)
        cursor = conn.execute("SELECT fatigue, morale, stress FROM pilot_rpg_stats WHERE pilotId = ?", (pilot.id,))
        row = cursor.fetchone()
        conn.close()
        
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 50)
        self.assertEqual(row[1], 80)
        self.assertEqual(row[2], 30)
        
        self.db.update_pilot_rpg_stats(pilot.id, 90, 20, 10)
        
        conn = sqlite3.connect(self.tmp_db.name)
        cursor = conn.execute("SELECT fatigue, morale, stress FROM pilot_rpg_stats WHERE pilotId = ?", (pilot.id,))
        row = cursor.fetchone()
        conn.close()
        
        self.assertEqual(row[0], 90)

    def test_mission_deduplication(self):
        """Testa que missões duplicadas (mesma data/hora/tipo/avião) são ignoradas pela DB."""
        pilot = WoFFPilot(name="Dedup Pilot")
        self.db.merge_and_write(pilot, [], [], [])
        
        m1 = WoFFMission(pilotId=pilot.id, date="1917-04-06", time="10:30", missionType="OP", aircraft="SE.5a")
        m2 = WoFFMission(pilotId=pilot.id, date="1917-04-06", time="10:30", missionType="OP", aircraft="SE.5a") # Duplicada
        m3 = WoFFMission(pilotId=pilot.id, date="1917-04-09", time="14:00", missionType="Art.Obs.", aircraft="SE.5a") # Única
        
        ok = self.db.merge_and_write(None, [m1, m2, m3], [], [])
        self.assertTrue(ok)
        
        conn = sqlite3.connect(self.tmp_db.name)
        cursor = conn.execute("SELECT COUNT(*) FROM missions WHERE pilotId = ?", (pilot.id,))
        count = cursor.fetchone()[0]
        conn.close()
        
        self.assertEqual(count, 2)

if __name__ == "__main__":
    unittest.main()