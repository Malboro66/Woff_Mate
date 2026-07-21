import unittest
import tempfile
import os
import sqlite3
from database import DatabaseManager
from models import WoFFPilot, WoFFMission

class TestDatabaseManager(unittest.TestCase):
    
    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close() # Fechar o handle para o SQLite poder abri-lo no Windows
        self.db = DatabaseManager(self.tmp_db.name)
    
    def tearDown(self):
        self.db = None # Limpar referência
        if os.path.exists(self.tmp_db.name):
            os.unlink(self.tmp_db.name)
    
    def test_merge_new_pilot(self):
        """Insere piloto novo."""
        pilot = WoFFPilot(name="John Doe", squadron="No. 56 Sqn")
        ok = self.db.merge_and_write(pilot, [], [], [])
        self.assertTrue(ok)
        
        # Verifica se foi inserido e o status padrão ("Active") foi aplicado
        status, rank = self.db.get_pilot_state("John Doe")
        self.assertIsNotNone(status)
        self.assertEqual(status, "Active")
    
    def test_merge_existing_pilot_by_name(self):
        """Atualiza piloto existente pelo nome usando COALESCE."""
        p1 = WoFFPilot(name="John Doe", squadron="No. 56 Sqn", rank="2nd Lieutenant")
        self.db.merge_and_write(p1, [], [], [])
        
        p2 = WoFFPilot(name="John Doe", squadron="No. 60 Sqn")  # Transferido
        self.db.merge_and_write(p2, [], [], [])
        
        # Buscar o piloto (mission_id vazio retorna o piloto mesmo sem missão)
        pilot_dict, _, _ = self.db.get_mission_and_history("John Doe", "")
        self.assertIsNotNone(pilot_dict)
        self.assertEqual(pilot_dict["squadron"], "No. 60 Sqn")
        # Verificar se o COALESCE manteve o rank antigo (pois p2 não enviou rank)
        self.assertEqual(pilot_dict["rank"], "2nd Lieutenant")
    
    def test_merge_pilot_by_source_file_glob(self):
        """Testa fallback GLOB para Pilot1 -> Pilot1Dossier.txt."""
        # Insere com nome real primeiro
        real = WoFFPilot(name="James Hartley", source_file="Pilot1Dossier.txt")
        self.db.merge_and_write(real, [], [], [])
        
        # Agora merge com nome genérico "Pilot 1"
        generic = WoFFPilot(name="Pilot 1", squadron="No. 56 Sqn")
        self.db.merge_and_write(generic, [], [], [])
        
        # Deve atualizar o mesmo registo, não criar novo
        pilot_dict, _, _ = self.db.get_mission_and_history("James Hartley", "")
        self.assertIsNotNone(pilot_dict)
        self.assertEqual(pilot_dict["squadron"], "No. 56 Sqn")
    
    def test_mission_foreign_key_constraint(self):
        """Testa que missão com pilotId inválido é rejeitada (INSERT OR IGNORE)."""
        mission = WoFFMission(pilotId="INVALID_ID", date="1917-04-06")
        ok = self.db.merge_and_write(None, [mission], [], [])
        
        # O método retorna True (não há exceção por causa do OR IGNORE), mas nada é inserido
        self.assertTrue(ok)
        
        # FIX: Usar uma ligação SQLite direta para validação, mantendo o encapsulamento do DatabaseManager
        conn = sqlite3.connect(self.tmp_db.name)
        cursor = conn.execute("SELECT COUNT(*) FROM missions WHERE pilotId = ?", ("INVALID_ID",))
        self.assertEqual(cursor.fetchone()[0], 0)
        conn.close()
    
    def test_rpg_stats_update(self):
        """Testa UPSERT de stats RPG."""
        pilot = WoFFPilot(name="Test Pilot")
        self.db.merge_and_write(pilot, [], [], [])
        
        # Insere stats
        self.db.update_pilot_rpg_stats(pilot.id, 50, 80, 30)
        
        # Validação direta
        conn = sqlite3.connect(self.tmp_db.name)
        cursor = conn.execute("SELECT fatigue, morale, stress FROM pilot_rpg_stats WHERE pilotId = ?", (pilot.id,))
        row = cursor.fetchone()
        conn.close()
        
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 50) # fatigue
        self.assertEqual(row[1], 80) # morale
        self.assertEqual(row[2], 30) # stress
        
        # Testar UPSERT (atualizar os mesmos stats)
        self.db.update_pilot_rpg_stats(pilot.id, 90, 20, 10)
        
        conn = sqlite3.connect(self.tmp_db.name)
        cursor = conn.execute("SELECT fatigue, morale, stress FROM pilot_rpg_stats WHERE pilotId = ?", (pilot.id,))
        row = cursor.fetchone()
        conn.close()
        
        self.assertEqual(row[0], 90) # Nova fatigue

if __name__ == "__main__":
    unittest.main()