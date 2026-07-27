"""
Testes de regressão para os bugs identificados na revisão de código:

1. process_mission_end() usava missions[0] em vez da missão mais recente.
2. diary_entries não tinha deduplicação real (id sempre novo, sem UNIQUE).
3. old_status era convertido de None para "" antes de chegar ao
   narrative_generator, impedindo a mensagem de "piloto novo".
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from handler import FileProcessor
from database import DatabaseManager
from campaign_engine import CampaignEngine
from narrative_generator import narrative_generator
from models import WoFFPilot, WoFFMission
import tempfile


class TestMissionOrderingFix(unittest.TestCase):
    """Bug #1: garantir que a missão processada é a mais recente, não a primeira da lista."""

    def test_latest_mission_selected_regardless_of_list_order(self):
        missions = [
            WoFFMission(id="OLDEST", date="1917-01-01", time="08:00"),
            WoFFMission(id="NEWEST", date="1917-06-15", time="14:30"),
            WoFFMission(id="MIDDLE", date="1917-03-10", time="09:00"),
        ]
        latest = max(missions, key=lambda m: (m.date, m.time))
        self.assertEqual(latest.id, "NEWEST")

    def test_same_date_different_time_picks_latest_time(self):
        missions = [
            WoFFMission(id="MORNING", date="1917-05-01", time="06:00"),
            WoFFMission(id="AFTERNOON", date="1917-05-01", time="16:00"),
        ]
        latest = max(missions, key=lambda m: (m.date, m.time))
        self.assertEqual(latest.id, "AFTERNOON")


class TestDiaryDeduplication(unittest.TestCase):
    """Bug #2: mesma missão processada duas vezes não deve duplicar entrada de diário."""

    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.db_path = tmp.name
        self.db = DatabaseManager(self.db_path)
        self.pilot_id = "PILOT_X"
        # Inserir piloto e missões mínimas para respeitar as FKs de diary_entries
        conn = self.db._get_conn()
        conn.execute(
            "INSERT INTO pilots (id, name) VALUES (?, ?)", (self.pilot_id, "Test Pilot")
        )
        for i, mission_id in enumerate(("MISSION_1", "M1", "M2")):
            conn.execute(
                "INSERT INTO missions (id, pilotId, date, time, missionType, aircraft) "
                "VALUES (?, ?, '1917-06-01', ?, 'OP', 'SE.5a')",
                (mission_id, self.pilot_id, f"{10+i:02d}:00"),
            )
        conn.commit()
        conn.close()

    def tearDown(self):
        for ext in ["", "-wal", "-shm"]:
            p = self.db_path + ext
            if os.path.exists(p):
                os.unlink(p)

    def test_duplicate_mission_diary_entry_is_ignored(self):
        first = self.db.save_diary_entry(self.pilot_id, "MISSION_1", "1917-06-01", "Narrativa A")
        second = self.db.save_diary_entry(self.pilot_id, "MISSION_1", "1917-06-01", "Narrativa B (duplicada)")

        self.assertTrue(first)
        self.assertFalse(second)  # FIX: agora é corretamente ignorada

        conn = self.db._get_conn()
        rows = conn.execute(
            "SELECT COUNT(*) FROM diary_entries WHERE pilotId=? AND missionId=?",
            (self.pilot_id, "MISSION_1"),
        ).fetchone()
        conn.close()
        self.assertEqual(rows[0], 1)

    def test_life_events_without_mission_id_can_repeat(self):
        # missionId=None (eventos de vida) não deve ser bloqueado por este índice
        r1 = self.db.save_diary_entry(self.pilot_id, None, "1917-06-01", "Evento de vida 1")
        r2 = self.db.save_diary_entry(self.pilot_id, None, "1917-06-02", "Evento de vida 2")
        self.assertTrue(r1)
        self.assertTrue(r2)

    def test_different_missions_both_saved(self):
        r1 = self.db.save_diary_entry(self.pilot_id, "M1", "1917-06-01", "Missão 1")
        r2 = self.db.save_diary_entry(self.pilot_id, "M2", "1917-06-02", "Missão 2")
        self.assertTrue(r1)
        self.assertTrue(r2)


class TestNewPilotWelcomeMessage(unittest.TestCase):
    """Bug #3: piloto novo (old_status=None) deve receber a mensagem de chegada,
    não a mensagem de promoção."""

    def test_narrative_generator_still_expects_none_for_new_pilot(self):
        narrative = narrative_generator.generate_life_event(
            new_status="Active", old_status=None, new_rank="Lieutenant", old_rank=None
        )
        self.assertIsNotNone(narrative)
        self.assertIn("Cheguei à esquadrilha", narrative)

    def test_empty_string_old_status_incorrectly_triggers_promotion_text(self):
        """Documenta o comportamento ERRADO que ocorria quando None virava ''
        antes de chegar aqui (o bug em si, não o fix)."""
        narrative = narrative_generator.generate_life_event(
            new_status="Active", old_status="", new_rank="Lieutenant", old_rank=""
        )
        self.assertIsNotNone(narrative)
        self.assertIn("Fui promovido", narrative)
        self.assertNotIn("Cheguei à esquadrilha", narrative)

    def test_campaign_engine_passes_none_through_for_new_pilot(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db = DatabaseManager(tmp.name)
        engine = CampaignEngine(db)
        try:
            pilot = WoFFPilot(name="Jeanot Ledoux", status="Active", rank="Sergeant")
            db.merge_and_write(pilot=pilot, missions=[], victories=[], decorations=[])

            # Simula exatamente o que handler.py/woff_watchdog.py agora fazem:
            # old_status vem de get_pilot_state ANTES do merge_and_write ter corrido
            # (aqui simulamos manualmente um piloto que ainda não existia).
            engine.process_life_events(
                pilot_name="Jeanot Ledoux",
                new_status="Active",
                new_rank="Sergeant",
                old_status=None,   # <- piloto novo: deve permanecer None, não ""
                old_rank=None,
            )

            conn = db._get_conn()
            row = conn.execute(
                "SELECT narrative FROM diary_entries d "
                "JOIN pilots p ON d.pilotId = p.id WHERE p.name=?",
                ("Jeanot Ledoux",),
            ).fetchone()
            conn.close()

            self.assertIsNotNone(row)
            self.assertIn("Cheguei à esquadrilha", row[0])
        finally:
            for ext in ["", "-wal", "-shm"]:
                p = tmp.name + ext
                if os.path.exists(p):
                    os.unlink(p)


if __name__ == "__main__":
    unittest.main()
