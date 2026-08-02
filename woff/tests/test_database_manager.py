import unittest
import tempfile
import os
import sqlite3
import gc
from typing import Any


from ..database import DatabaseManager
from ..models import WoFFPilot, WoFFMission, WoFFVictory, WoFFDecoration, WoFFWingman

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

    def test_merge_and_write_persists_all_entities(self):
        """Regression: merge_and_write keeps legacy write behavior across entities."""
        pilot = WoFFPilot(
            id="pilot-regression",
            name="Regression Pilot",
            rank="Captain",
            squadron="No. 1 Sqn",
            source_file="Pilot9Dossier.txt",
        )
        mission = WoFFMission(
            id="mission-regression",
            date="1917-05-01",
            time="08:15",
            missionType="Patrol",
            aircraft="Sopwith Camel",
            damageReceived=True,
            woundsReceived=False,
        )
        victory = WoFFVictory(
            id="victory-regression",
            date="1917-05-01",
            time="08:40",
            missionId=mission.id,
            enemyType="Albatros D.III",
            victoryType="Destroyed",
            confirmed=True,
        )
        decoration = WoFFDecoration(
            id="decoration-regression",
            name="Military Cross",
            date="1917-05-02",
            citation="Gallantry in action",
        )
        wingman = WoFFWingman(
            id="wingman-regression",
            rank="Lt",
            fName="Arthur",
            sName="Reed",
            skill=55,
            morale=70,
        )

        pilot_id = self.db.merge_and_write(
            pilot, [mission], [victory], [decoration], [wingman]
        )

        self.assertEqual(pilot_id, pilot.id)
        conn = sqlite3.connect(self.tmp_db.name)
        rows = {
            "pilots": conn.execute(
                "SELECT id, name, rank, squadron FROM pilots WHERE id = ?",
                (pilot.id,),
            ).fetchone(),
            "missions": conn.execute(
                "SELECT pilotId, damageReceived, woundsReceived FROM missions WHERE id = ?",
                (mission.id,),
            ).fetchone(),
            "victories": conn.execute(
                "SELECT pilotId, confirmed FROM victories WHERE id = ?",
                (victory.id,),
            ).fetchone(),
            "decorations": conn.execute(
                "SELECT pilotId, name FROM decorations WHERE id = ?",
                (decoration.id,),
            ).fetchone(),
            "squad_members": conn.execute(
                "SELECT pilotId, fName, sName, morale FROM squad_members WHERE id = ?",
                (wingman.id,),
            ).fetchone(),
        }
        conn.close()

        self.assertEqual(rows["pilots"], (pilot.id, pilot.name, pilot.rank, pilot.squadron))
        self.assertEqual(rows["missions"], (pilot.id, 1, 0))
        self.assertEqual(rows["victories"], (pilot.id, 1))
        self.assertEqual(rows["decorations"], (pilot.id, decoration.name))
        self.assertEqual(rows["squad_members"], (pilot.id, wingman.fName, wingman.sName, wingman.morale))

    def test_mission_repository_read_methods_exist(self):
        """MissionRepository exposes its read APIs and returns persisted mission data."""
        pilot = WoFFPilot(name="Mission Repo Pilot")
        mission = WoFFMission(
            pilotId=pilot.id,
            date="1917-06-01",
            time="09:00",
            missionType="Escort",
            aircraft="SE.5a",
        )
        self.db.merge_and_write(pilot, [mission], [], [])

        self.assertEqual(self.db._missions.count_by_pilot(pilot.id), 1)
        missions = self.db._missions.get_missions_by_pilot(pilot.id)
        self.assertEqual(len(missions), 1)
        self.assertEqual(missions[0]["id"], mission.id)

if __name__ == "__main__":
    unittest.main()
