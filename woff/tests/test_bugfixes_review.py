"""
Testes de regressão para os bugs identificados na revisão de código:

1. process_mission_end() deve receber a missão mais recente nos pontos de chamada reais.
2. diary_entries não tinha deduplicação real (id sempre novo, sem UNIQUE).
3. old_status era convertido de None para "" antes de chegar ao
   narrative_generator, impedindo a mensagem de "piloto novo".
"""
import os
import unittest
import sqlite3


from ..handler import FileProcessor, get_latest_mission_id
from ..database import DatabaseManager
from ..campaign_engine import CampaignEngine
from ..narrative_generator import narrative_generator
from ..models import WoFFPilot, WoFFMission
import tempfile
from unittest.mock import MagicMock


class TestMissionOrderingFix(unittest.TestCase):
    """Bug #1: a seleção da missão mais recente é centralizada e usada pelos fluxos reais."""

    def test_latest_mission_selected_regardless_of_list_order(self):
        missions = [
            WoFFMission(id="OLDEST", date="1917-01-01", time="08:00"),
            WoFFMission(id="NEWEST", date="1917-06-15", time="14:30"),
            WoFFMission(id="MIDDLE", date="1917-03-10", time="09:00"),
        ]
        parser = MagicMock(missions=missions)
        self.assertEqual(get_latest_mission_id(parser), "NEWEST")

    def test_same_date_different_time_picks_latest_time(self):
        missions = [
            WoFFMission(id="MORNING", date="1917-05-01", time="06:00"),
            WoFFMission(id="AFTERNOON", date="1917-05-01", time="16:00"),
        ]
        parser = MagicMock(missions=missions)
        self.assertEqual(get_latest_mission_id(parser), "AFTERNOON")

    def test_empty_mission_list_returns_none(self):
        parser = MagicMock(missions=[])
        self.assertIsNone(get_latest_mission_id(parser))


class TestLatestMissionIntegration(unittest.TestCase):
    """Garante que FileProcessor envia ao CampaignEngine a missão mais recente."""

    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.db_path = tmp.name
        self.db = DatabaseManager(self.db_path)
        self.engine = MagicMock(spec=CampaignEngine)
        self.processor = FileProcessor(self.db, self.engine)

    def tearDown(self):
        self.db.close()
        for ext in ["", "-wal", "-shm", "-journal"]:
            p = self.db_path + ext
            if os.path.exists(p):
                os.unlink(p)

    def test_integration_latest_mission_passed_to_campaign_from_xml(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<Campaign>
  <Pilot><PilotName>Latest XML Pilot</PilotName><Status>Active</Status></Pilot>
  <Missions>
    <Mission><Date>1917-01-01</Date><Time>08:00</Time><Type>Patrol</Type></Mission>
    <Mission><Date>1917-06-15</Date><Time>14:30</Time><Type>Patrol</Type></Mission>
  </Missions>
</Campaign>
"""
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(xml)
            path = f.name
        try:
            self.processor._process_xml(path)
        finally:
            os.unlink(path)

        self.engine.process_mission_end.assert_called_once()
        pilot_id, mission_id = self.engine.process_mission_end.call_args.args
        conn = self.db._get_conn()
        row = conn.execute("SELECT date, time FROM missions WHERE id=? AND pilotId=?", (mission_id, pilot_id)).fetchone()
        self.assertEqual(tuple(row), ("1917-06-15", "14:30"))

    def test_integration_latest_mission_passed_to_campaign_from_text_log(self):
        pilot = WoFFPilot(name="Real Text Pilot", source_file="Pilot1Dossier.txt")
        self.db.merge_and_write(pilot=pilot, missions=[], victories=[], decorations=[])
        log_text = "Header\n" + "\n".join([
            "01;01;1917;8;00;A;B;Patrol;SE.5a;X;45;Y;Z;No. 56 Squadron RFC;;;;;;Old mission",
            "15;06;1917;14;30;A;B;Patrol;SE.5a;X;45;Y;Z;No. 56 Squadron RFC;;;;;;Latest mission",
        ])
        tmp_dir = tempfile.mkdtemp()
        path = os.path.join(tmp_dir, "Pilot1Log.txt")
        try:
            with open(path, "w", encoding="cp1252") as f:
                f.write(log_text)
            self.processor._process_text(path, "pilot1log.txt")
        finally:
            import shutil
            shutil.rmtree(tmp_dir)

        self.engine.process_mission_end.assert_called_once()
        pilot_id, mission_id = self.engine.process_mission_end.call_args.args
        conn = self.db._get_conn()
        row = conn.execute("SELECT date, time FROM missions WHERE id=? AND pilotId=?", (mission_id, pilot_id)).fetchone()
        self.assertEqual(tuple(row), ("1917-06-15", "14:30"))


class TestDiaryDeduplication(unittest.TestCase):
    """Bug #2: mesma missão processada duas vezes não deve duplicar entrada de diário."""

    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.db_path = tmp.name
        self.db = DatabaseManager(self.db_path)
        self.pilot_id = "PILOT_X"
        # Inserir piloto e missões mínimas para respeitar as FKs de diary_entries.
        # Usa uma conexão independente para não manipular a conexão thread-local
        # privada do DatabaseManager durante a preparação do fixture.
        fixture_conn = sqlite3.connect(self.db.db_path)
        try:
            fixture_conn.execute("PRAGMA foreign_keys=ON;")
            fixture_conn.execute(
                "INSERT INTO pilots (id, name) VALUES (?, ?)",
                (self.pilot_id, "Test Pilot"),
            )
            for i, mission_id in enumerate(("MISSION_1", "M1", "M2")):
                fixture_conn.execute(
                    "INSERT INTO missions (id, pilotId, date, time, missionType, aircraft) "
                    "VALUES (?, ?, '1917-06-01', ?, 'OP', 'SE.5a')",
                    (mission_id, self.pilot_id, f"{10+i:02d}:00"),
                )
            fixture_conn.commit()
        finally:
            fixture_conn.close()

    def tearDown(self):
        self.db.close()
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

    def test_database_manager_recovers_from_externally_closed_connection(self):
        conn = self.db._get_conn()
        conn.close()

        inserted = self.db.save_diary_entry(
            self.pilot_id, "M1", "1917-06-01", "Narrativa após reconexão"
        )

        self.assertTrue(inserted)

    def test_database_manager_close_is_idempotent(self):
        self.db.close()
        self.db.close()

        inserted = self.db.save_diary_entry(
            self.pilot_id, "M2", "1917-06-01", "Narrativa após close idempotente"
        )

        self.assertTrue(inserted)


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

            self.assertIsNotNone(row)
            self.assertIn("Cheguei à esquadrilha", row[0])
        finally:
            db.close()
            for ext in ["", "-wal", "-shm", "-journal"]:
                p = tmp.name + ext
                if os.path.exists(p):
                    os.unlink(p)


if __name__ == "__main__":
    unittest.main()
