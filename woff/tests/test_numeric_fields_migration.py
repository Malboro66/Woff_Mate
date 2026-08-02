import sqlite3

from woff.database import DatabaseManager
from woff.models import WoFFMission, WoFFPilot, WoFFWingman
from woff.rpg_system import RPGSystem


def test_numeric_model_fields_support_arithmetic_without_casting():
    pilot = WoFFPilot(missions=2, flminutes=40, claimsCount=1, killsCount=1, skill=55, reputation=10)
    mission = WoFFMission(enemyContacts=3, claimsCount=2)
    wingman = WoFFWingman(skill=45, morale=70, missions=4, flminutes=120)

    assert pilot.missions + pilot.claimsCount == 3
    assert mission.enemyContacts * 4 == 12
    assert wingman.morale + wingman.skill == 115


def test_rpg_accepts_integer_mission_counts_without_casting():
    rpg = RPGSystem()
    missions = [{"claimsCount": 1, "enemyContacts": 3, "woundsReceived": False, "damageReceived": False, "result": ""}]

    assert rpg.calculate_morale(missions, "Active") == 80
    assert rpg.calculate_stress(missions) == 12


def test_old_text_numeric_database_is_migrated_without_data_loss(tmp_path):
    db_path = tmp_path / "old.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE pilots (
            id TEXT PRIMARY KEY, name TEXT UNIQUE, fName TEXT, sName TEXT,
            nation TEXT, rank TEXT, squadron TEXT, aircraft TEXT,
            aerodrome TEXT, sector TEXT, startDate TEXT, enlisted TEXT,
            status TEXT, notes TEXT, photo TEXT, birthDate TEXT,
            birthPlace TEXT, missions TEXT, flminutes TEXT,
            claimsCount TEXT, killsCount TEXT, skill TEXT,
            reputation TEXT, source_file TEXT, last_updated TEXT
        );
        CREATE TABLE missions (
            id TEXT PRIMARY KEY, pilotId TEXT, date TEXT, time TEXT,
            missionType TEXT, aircraft TEXT, duration TEXT, altitude TEXT,
            sector TEXT, squadron TEXT, weather TEXT, enemyContacts TEXT,
            claimsCount TEXT, result TEXT, damageReceived INTEGER,
            woundsReceived INTEGER, notes TEXT, source_file TEXT,
            UNIQUE(pilotId, date, time, missionType, aircraft),
            FOREIGN KEY(pilotId) REFERENCES pilots(id)
        );
        CREATE TABLE squad_members (
            id TEXT PRIMARY KEY, pilotId TEXT, rank TEXT, fName TEXT,
            sName TEXT, skill TEXT, morale TEXT, status TEXT,
            missions TEXT, flminutes TEXT, bio TEXT,
            UNIQUE(pilotId, fName, sName)
        );
        """
    )
    conn.execute("INSERT INTO pilots (id, name, missions, flminutes, claimsCount, killsCount, skill, reputation) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ("p1", "Pilot", "7", "180", "2", "1", "55", "900"))
    conn.execute("INSERT INTO missions (id, pilotId, date, time, missionType, aircraft, enemyContacts, claimsCount, damageReceived, woundsReceived) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ("m1", "p1", "1917-01-01", "08:00", "Patrol", "Camel", "3", "1", 0, 0))
    conn.execute("INSERT INTO squad_members (id, pilotId, fName, sName, skill, morale, missions, flminutes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ("w1", "p1", "A", "B", "45", "70", "4", "120"))
    conn.commit()
    conn.close()

    db = DatabaseManager(str(db_path))
    db.close()

    conn = sqlite3.connect(db_path)
    pilot_row = conn.execute("SELECT missions, flminutes, claimsCount, killsCount, skill, reputation FROM pilots WHERE id='p1'").fetchone()
    mission_row = conn.execute("SELECT enemyContacts, claimsCount FROM missions WHERE id='m1'").fetchone()
    wingman_row = conn.execute("SELECT skill, morale, missions, flminutes FROM squad_members WHERE id='w1'").fetchone()
    pilot_types = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(pilots)")}
    mission_types = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(missions)")}
    wingman_types = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(squad_members)")}
    conn.close()

    assert pilot_row == (7, 180, 2, 1, 55, 900)
    assert mission_row == (3, 1)
    assert wingman_row == (45, 70, 4, 120)
    assert pilot_types["missions"] == "INTEGER"
    assert mission_types["enemyContacts"] == "INTEGER"
    assert wingman_types["morale"] == "INTEGER"
