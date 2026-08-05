import os
import sqlite3
from pathlib import Path

import pytest

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
    rpg = RPGSystem(seed=0)
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


# Issue #5 safe numeric migration regression coverage


def _connect(path):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _old_schema(conn):
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '2.0');
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
            UNIQUE(pilotId, fName, sName),
            FOREIGN KEY(pilotId) REFERENCES pilots(id)
        );
        CREATE UNIQUE INDEX idx_squad_custom_unique ON squad_members(pilotId, fName, sName, status);
        CREATE INDEX idx_missions_pilot_date ON missions(pilotId, date);
        """
    )


def _seed_valid_rows(conn):
    conn.execute("INSERT INTO pilots (id, name, missions, flminutes, claimsCount, killsCount, skill, reputation) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ("p1", "Pilot", "7", "180", "2", "1", "55", "900"))
    conn.execute("INSERT INTO missions (id, pilotId, date, time, missionType, aircraft, enemyContacts, claimsCount, damageReceived, woundsReceived) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ("m1", "p1", "1917-01-01", "08:00", "Patrol", "Camel", "3", "1", 0, 0))
    conn.execute("INSERT INTO squad_members (id, pilotId, fName, sName, status, skill, morale, missions, flminutes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", ("w1", "p1", "A", "B", "Active", "45", "70", "4", "120"))


def _dump(path):
    conn = sqlite3.connect(path)
    try:
        return "\n".join(conn.iterdump())
    finally:
        conn.close()


def test_new_database_has_integer_numeric_columns_and_schema_version(tmp_path):
    db_path = tmp_path / "new.sqlite"
    db = DatabaseManager(str(db_path))
    db.close()
    conn = _connect(db_path)
    try:
        pilot_types = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(pilots)")}
        assert pilot_types["missions"] == "INTEGER"
        assert conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone() == ("3.1",)
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        conn.close()


def test_old_text_numeric_schema_migrates_values_foreign_keys_and_indexes(tmp_path):
    db_path = tmp_path / "old.sqlite"
    conn = _connect(db_path)
    _old_schema(conn)
    _seed_valid_rows(conn)
    conn.commit(); conn.close()

    db = DatabaseManager(str(db_path)); db.close()

    conn = _connect(db_path)
    try:
        assert conn.execute("SELECT missions, flminutes, claimsCount, killsCount, skill, reputation FROM pilots WHERE id='p1'").fetchone() == (7, 180, 2, 1, 55, 900)
        assert conn.execute("SELECT enemyContacts, claimsCount FROM missions WHERE id='m1'").fetchone() == (3, 1)
        assert conn.execute("SELECT skill, morale, missions, flminutes FROM squad_members WHERE id='w1'").fetchone() == (45, 70, 4, 120)
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(missions)")}
        assert "idx_missions_pilot_date" in indexes
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO missions (id, pilotId) VALUES ('bad', 'missing')")
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("value", "expected"),
    [("", None), (None, None), ("-4", -4), (" 12 ", 12)],
)
def test_empty_null_negative_and_spaced_numeric_values_are_explicitly_handled(tmp_path, value, expected):
    db_path = tmp_path / "values.sqlite"
    conn = _connect(db_path)
    _old_schema(conn)
    conn.execute("INSERT INTO pilots (id, name, missions) VALUES ('p1', 'Pilot', ?)", (value,))
    conn.commit(); conn.close()

    db = DatabaseManager(str(db_path)); db.close()

    conn = _connect(db_path)
    try:
        assert conn.execute("SELECT missions FROM pilots WHERE id='p1'").fetchone() == (expected,)
    finally:
        conn.close()


def test_invalid_numeric_values_abort_without_silent_conversion_or_version_update(tmp_path):
    db_path = tmp_path / "invalid.sqlite"
    conn = _connect(db_path)
    _old_schema(conn)
    conn.execute("INSERT INTO pilots (id, name, missions) VALUES ('p1', 'Pilot', 'abc')")
    conn.commit(); conn.close()
    before = _dump(db_path)

    with pytest.raises(ValueError, match="Invalid integer values"):
        DatabaseManager(str(db_path))

    assert _dump(db_path) == before
    conn = _connect(db_path)
    try:
        assert conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone() == ("2.0",)
    finally:
        conn.close()


def test_numeric_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "idempotent.sqlite"
    conn = _connect(db_path)
    _old_schema(conn); _seed_valid_rows(conn)
    conn.commit(); conn.close()

    db = DatabaseManager(str(db_path)); db.close()
    after_first = _dump(db_path)
    db = DatabaseManager(str(db_path)); db.close()
    assert _dump(db_path) == after_first


def test_simulated_rebuild_failure_restores_original_database_and_schema_version(tmp_path, monkeypatch):
    db_path = tmp_path / "failure.sqlite"
    conn = _connect(db_path)
    _old_schema(conn); _seed_valid_rows(conn)
    conn.commit(); conn.close()
    before = _dump(db_path)

    original_create = DatabaseManager._create_rebuild_table_from_schema

    def fail_for_missions(self, cursor, table, new_table, numeric_columns):
        if table == "missions":
            raise RuntimeError("boom")
        return original_create(self, cursor, table, new_table, numeric_columns)

    monkeypatch.setattr(DatabaseManager, "_create_rebuild_table_from_schema", fail_for_missions)

    with pytest.raises(RuntimeError, match="boom"):
        DatabaseManager(str(db_path))

    assert _dump(db_path) == before
    conn = _connect(db_path)
    try:
        assert conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone() == ("2.0",)
        assert conn.execute("PRAGMA foreign_keys").fetchone() == (1,)
    finally:
        conn.close()


@pytest.mark.parametrize(
    "value",
    [str(2 ** 63), str(-(2 ** 63) - 1), "１２", "١٢"],
)
def test_ascii_signed_64_bit_integer_policy_rejects_overflow_underflow_and_unicode_digits(tmp_path, value):
    db_path = tmp_path / "range.sqlite"
    conn = _connect(db_path)
    _old_schema(conn)
    conn.execute("INSERT INTO pilots (id, name, missions) VALUES ('p1', 'Pilot', ?)", (value,))
    conn.commit(); conn.close()

    with pytest.raises(ValueError, match="Invalid integer values"):
        DatabaseManager(str(db_path))

    conn = _connect(db_path)
    try:
        assert conn.execute("SELECT missions FROM pilots WHERE id='p1'").fetchone() == (value,)
        assert conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone() == ("2.0",)
    finally:
        conn.close()


def test_external_foreign_keys_with_and_without_children_survive_parent_rebuild(tmp_path):
    db_path = tmp_path / "external_fk.sqlite"
    conn = _connect(db_path)
    _old_schema(conn)
    _seed_valid_rows(conn)
    conn.executescript(
        """
        CREATE TABLE pilot_notes (
            id TEXT PRIMARY KEY,
            pilotId TEXT,
            note TEXT,
            FOREIGN KEY(pilotId) REFERENCES pilots(id)
        );
        CREATE TABLE empty_pilot_notes (
            id TEXT PRIMARY KEY,
            pilotId TEXT,
            note TEXT,
            FOREIGN KEY(pilotId) REFERENCES pilots(id)
        );
        INSERT INTO pilot_notes (id, pilotId, note) VALUES ('n1', 'p1', 'child row');
        """
    )
    conn.commit(); conn.close()

    db = DatabaseManager(str(db_path)); db.close()

    conn = _connect(db_path)
    try:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT pilotId FROM pilot_notes WHERE id='n1'").fetchone() == ("p1",)
        assert conn.execute("PRAGMA foreign_key_list(pilot_notes)").fetchone()[2] == "pilots"
        assert conn.execute("PRAGMA foreign_key_list(empty_pilot_notes)").fetchone()[2] == "pilots"
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO pilot_notes (id, pilotId) VALUES ('bad', 'missing')")
    finally:
        conn.close()


def test_custom_unique_index_triggers_and_views_are_recreated_after_rebuild(tmp_path):
    db_path = tmp_path / "objects.sqlite"
    conn = _connect(db_path)
    _old_schema(conn)
    _seed_valid_rows(conn)
    conn.executescript(
        """
        CREATE TABLE pilot_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, pilotId TEXT, action TEXT);
        CREATE TRIGGER trg_pilots_audit AFTER INSERT ON pilots
        BEGIN
            INSERT INTO pilot_audit (pilotId, action) VALUES (NEW.id, 'insert');
        END;
        CREATE VIEW pilot_names AS SELECT id, name, missions FROM pilots;
        """
    )
    conn.commit(); conn.close()

    db = DatabaseManager(str(db_path)); db.close()

    conn = _connect(db_path)
    try:
        assert "idx_squad_custom_unique" in {row[1] for row in conn.execute("PRAGMA index_list(squad_members)")}
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO squad_members (id, pilotId, fName, sName, status) VALUES ('w2', 'p1', 'A', 'B', 'Active')"
            )
        conn.execute("INSERT INTO pilots (id, name, missions) VALUES ('p2', 'Pilot 2', 1)")
        assert conn.execute("SELECT pilotId, action FROM pilot_audit WHERE pilotId='p2'").fetchone() == ("p2", "insert")
        assert conn.execute("SELECT missions FROM pilot_names WHERE id='p1'").fetchone() == (7,)
    finally:
        conn.close()


def test_backup_is_created_only_for_pending_migration_and_backup_path_is_git_ignored(tmp_path):
    db_path = tmp_path / "backup.sqlite"
    db = DatabaseManager(str(db_path)); db.close()
    backup_dir = tmp_path / ".woff-migration-backups"
    assert not backup_dir.exists()

    conn = _connect(db_path)
    conn.execute("UPDATE meta SET value='2.0' WHERE key='schema_version'")
    conn.commit(); conn.close()
    db = DatabaseManager(str(db_path)); db.close()
    assert not backup_dir.exists()

    old_path = tmp_path / "old_backup.sqlite"
    conn = _connect(old_path)
    _old_schema(conn)
    _seed_valid_rows(conn)
    conn.commit(); conn.close()
    db = DatabaseManager(str(old_path)); db.close()
    backups = sorted((tmp_path / ".woff-migration-backups").glob("*.backup.sqlite"))
    assert len(backups) == 1
    assert backups[0].suffix == ".sqlite"
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    assert ".woff-migration-backups/" in gitignore
    assert "*.backup.sqlite" in gitignore


def test_backups_are_not_overwritten_on_repeated_failed_migrations(tmp_path):
    db_path = tmp_path / "no_overwrite.sqlite"
    conn = _connect(db_path)
    _old_schema(conn)
    conn.execute("INSERT INTO pilots (id, name, missions) VALUES ('p1', 'Pilot', 'bad')")
    conn.commit(); conn.close()

    for _ in range(2):
        with pytest.raises(ValueError, match="Invalid integer values"):
            DatabaseManager(str(db_path))

    backups = sorted((tmp_path / ".woff-migration-backups").glob("*.backup.sqlite"))
    assert len(backups) == 2
    assert backups[0].name != backups[1].name


def test_restore_removes_sidecars_and_recovers_from_committed_partial_failure(tmp_path, monkeypatch):
    db_path = tmp_path / "restore.sqlite"
    conn = _connect(db_path)
    _old_schema(conn)
    _seed_valid_rows(conn)
    conn.commit(); conn.close()
    before = _dump(db_path)
    for suffix in ("-wal", "-shm", "-journal"):
        Path(f"{db_path}{suffix}").write_text("sidecar")

    def commit_partial_change(self, cursor):
        cursor.execute("DROP TABLE pilots")
        cursor.connection.commit()
        raise RuntimeError("committed partial failure")

    monkeypatch.setattr(DatabaseManager, "_migrate_numeric_column_types", commit_partial_change)

    with pytest.raises(RuntimeError, match="committed partial failure"):
        DatabaseManager(str(db_path))

    assert _dump(db_path) == before
    assert list((tmp_path / ".woff-migration-backups").glob("*.backup.sqlite"))


def test_wal_committed_transaction_with_active_reader_migrates_without_checkpoint_loss(tmp_path):
    db_path = tmp_path / "wal_busy.sqlite"
    conn = _connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    _old_schema(conn)
    _seed_valid_rows(conn)
    conn.commit()
    reader = sqlite3.connect(db_path)
    reader.execute("BEGIN")
    assert reader.execute("SELECT COUNT(*) FROM pilots").fetchone() == (1,)
    conn.execute("INSERT INTO pilots (id, name, missions) VALUES ('p2', 'Pilot 2', '8')")
    conn.commit()
    assert Path(f"{db_path}-wal").exists()

    db = DatabaseManager(str(db_path)); db.close()
    reader.close(); conn.close()

    conn = _connect(db_path)
    try:
        assert conn.execute("SELECT missions FROM pilots WHERE id='p2'").fetchone() == (8,)
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        conn.close()


def test_concurrent_write_between_backup_and_migration_is_blocked_by_same_transaction(tmp_path, monkeypatch):
    db_path = tmp_path / "concurrent.sqlite"
    conn = _connect(db_path)
    _old_schema(conn)
    _seed_valid_rows(conn)
    conn.commit(); conn.close()
    attempted = []
    original_backup = DatabaseManager._backup_existing_database

    def backup_and_try_concurrent_write(self):
        backup_path = original_backup(self)
        other = sqlite3.connect(db_path, timeout=0)
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                other.execute("INSERT INTO pilots (id, name, missions) VALUES ('p2', 'Other', '1')")
            attempted.append(True)
        finally:
            other.close()
        return backup_path

    monkeypatch.setattr(DatabaseManager, "_backup_existing_database", backup_and_try_concurrent_write)

    db = DatabaseManager(str(db_path)); db.close()
    assert attempted == [True]
    conn = _connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM pilots WHERE id='p2'").fetchone() == (0,)
    finally:
        conn.close()


def test_legitimate_new_pilots_table_collision_is_not_dropped(tmp_path):
    db_path = tmp_path / "collision.sqlite"
    conn = _connect(db_path)
    _old_schema(conn)
    _seed_valid_rows(conn)
    conn.execute("CREATE TABLE new_pilots (id TEXT PRIMARY KEY, marker TEXT)")
    conn.execute("INSERT INTO new_pilots (id, marker) VALUES ('keep', 'do not drop')")
    conn.commit(); conn.close()

    db = DatabaseManager(str(db_path)); db.close()

    conn = _connect(db_path)
    try:
        assert conn.execute("SELECT marker FROM new_pilots WHERE id='keep'").fetchone() == ("do not drop",)
        assert conn.execute("SELECT missions FROM pilots WHERE id='p1'").fetchone() == (7,)
    finally:
        conn.close()


def test_rebuild_preserves_custom_check_not_null_default_and_squad_members_fk(tmp_path):
    db_path = tmp_path / "schema_preserve.sqlite"
    conn = _connect(db_path)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '2.0');
        CREATE TABLE pilots (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE,
            missions TEXT NOT NULL DEFAULT '0' CHECK(CAST(missions AS INTEGER) >= 0)
        );
        CREATE TABLE missions (
            id TEXT PRIMARY KEY,
            pilotId TEXT,
            enemyContacts TEXT DEFAULT '0',
            claimsCount TEXT DEFAULT '0',
            FOREIGN KEY(pilotId) REFERENCES pilots(id)
        );
        CREATE TABLE squad_members (
            id TEXT PRIMARY KEY,
            pilotId TEXT NOT NULL,
            fName TEXT,
            sName TEXT,
            skill TEXT NOT NULL DEFAULT '1' CHECK(CAST(skill AS INTEGER) >= 0),
            morale TEXT DEFAULT '50',
            missions TEXT DEFAULT '0',
            flminutes TEXT DEFAULT '0',
            UNIQUE(pilotId, fName, sName),
            FOREIGN KEY(pilotId) REFERENCES pilots(id)
        );
        INSERT INTO pilots (id, name, missions) VALUES ('p1', 'Pilot', '7');
        INSERT INTO squad_members (id, pilotId, fName, sName, skill) VALUES ('w1', 'p1', 'A', 'B', '2');
        """
    )
    conn.commit(); conn.close()

    db = DatabaseManager(str(db_path)); db.close()

    conn = _connect(db_path)
    try:
        pilot_cols = {row[1]: row for row in conn.execute("PRAGMA table_info(pilots)")}
        squad_cols = {row[1]: row for row in conn.execute("PRAGMA table_info(squad_members)")}
        assert pilot_cols["missions"][2] == "INTEGER"
        assert pilot_cols["missions"][3] == 1
        assert squad_cols["skill"][2] == "INTEGER"
        assert squad_cols["skill"][3] == 1
        assert conn.execute("PRAGMA foreign_key_list(squad_members)").fetchone()[2] == "pilots"
        conn.execute("INSERT INTO pilots (id, name) VALUES ('p2', 'Default Pilot')")
        assert conn.execute("SELECT missions FROM pilots WHERE id='p2'").fetchone() == (0,)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO pilots (id, name, missions) VALUES ('p3', 'Bad', -1)")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO squad_members (id, pilotId) VALUES ('bad', 'missing')")
    finally:
        conn.close()


def test_restore_replace_failure_keeps_current_database_and_backup(tmp_path, monkeypatch):
    db_path = tmp_path / "replace_fail.sqlite"
    conn = _connect(db_path)
    _old_schema(conn)
    conn.execute("INSERT INTO pilots (id, name, missions) VALUES ('p1', 'Pilot', 'bad')")
    conn.commit(); conn.close()
    before = _dump(db_path)
    original_replace = os.replace

    def fail_restore_replace(src, dst):
        if str(src).endswith(".restore.tmp") and Path(dst) == db_path:
            raise OSError("replace failed")
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_restore_replace)

    with pytest.raises(ValueError, match="Invalid integer values"):
        DatabaseManager(str(db_path))

    assert _dump(db_path) == before
    assert list((tmp_path / ".woff-migration-backups").glob("*.backup.sqlite"))


def test_restore_quarantine_unlink_failure_keeps_restored_database_and_backup(tmp_path, monkeypatch):
    db_path = tmp_path / "unlink_fail.sqlite"
    conn = _connect(db_path)
    _old_schema(conn)
    conn.execute("INSERT INTO pilots (id, name, missions) VALUES ('p1', 'Pilot', 'bad')")
    conn.commit(); conn.close()
    before = _dump(db_path)
    original_unlink = Path.unlink

    def fail_quarantine_unlink(self, *args, **kwargs):
        if ".quarantine" in self.name:
            raise OSError("unlink failed")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_quarantine_unlink)

    with pytest.raises(ValueError, match="Invalid integer values"):
        DatabaseManager(str(db_path))

    assert _dump(db_path) == before
    assert list((tmp_path / ".woff-migration-backups").glob("*.backup.sqlite"))


def test_views_with_similar_names_and_view_dependencies_are_preserved(tmp_path):
    db_path = tmp_path / "views.sqlite"
    conn = _connect(db_path)
    _old_schema(conn)
    _seed_valid_rows(conn)
    conn.executescript(
        """
        CREATE VIEW pilot_base AS SELECT id, missions FROM pilots;
        CREATE VIEW pilot_nested AS SELECT id, missions FROM pilot_base;
        CREATE VIEW pilots_archive AS SELECT 'not dependent' AS label;
        """
    )
    conn.commit(); conn.close()

    db = DatabaseManager(str(db_path)); db.close()

    conn = _connect(db_path)
    try:
        assert conn.execute("SELECT missions FROM pilot_nested WHERE id='p1'").fetchone() == (7,)
        assert conn.execute("SELECT label FROM pilots_archive").fetchone() == ("not dependent",)
    finally:
        conn.close()


def test_windows_style_restore_uses_sqlite_backup_without_replacing_active_files(tmp_path, monkeypatch):
    db_path = tmp_path / "windows_restore.sqlite"
    conn = _connect(db_path)
    _old_schema(conn)
    conn.execute("INSERT INTO pilots (id, name, missions) VALUES ('p1', 'Pilot', 'bad')")
    conn.commit(); conn.close()
    before = _dump(db_path)

    def forbidden_replace(*args, **kwargs):
        raise AssertionError("restore must not replace database files")

    monkeypatch.setattr(os, "replace", forbidden_replace)

    with pytest.raises(ValueError, match="Invalid integer values"):
        DatabaseManager(str(db_path))

    assert _dump(db_path) == before
    assert list((tmp_path / ".woff-migration-backups").glob("*.backup.sqlite"))


def test_instead_of_insert_trigger_on_view_is_recreated_after_view(tmp_path):
    db_path = tmp_path / "instead_of.sqlite"
    conn = _connect(db_path)
    _old_schema(conn)
    _seed_valid_rows(conn)
    conn.executescript(
        """
        CREATE VIEW pilot_insert_view AS SELECT id, name, missions FROM pilots;
        CREATE TRIGGER trg_pilot_insert_view
        INSTEAD OF INSERT ON pilot_insert_view
        BEGIN
            INSERT INTO pilots (id, name, missions) VALUES (NEW.id, NEW.name, NEW.missions);
        END;
        """
    )
    conn.commit(); conn.close()

    db = DatabaseManager(str(db_path)); db.close()

    conn = _connect(db_path)
    try:
        conn.execute("INSERT INTO pilot_insert_view (id, name, missions) VALUES ('p2', 'Pilot 2', 3)")
        assert conn.execute("SELECT missions FROM pilots WHERE id='p2'").fetchone() == (3,)
    finally:
        conn.close()


def test_create_table_without_space_before_parenthesis_is_supported(tmp_path):
    db_path = tmp_path / "no_space.sqlite"
    conn = _connect(db_path)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '2.0');
        CREATE TABLE pilots(id TEXT PRIMARY KEY, name TEXT UNIQUE, missions TEXT);
        CREATE TABLE missions(id TEXT PRIMARY KEY, pilotId TEXT, enemyContacts TEXT, claimsCount TEXT,
            FOREIGN KEY(pilotId) REFERENCES pilots(id));
        CREATE TABLE squad_members(id TEXT PRIMARY KEY, pilotId TEXT, skill TEXT, morale TEXT, missions TEXT,
            flminutes TEXT, FOREIGN KEY(pilotId) REFERENCES pilots(id));
        INSERT INTO pilots (id, name, missions) VALUES ('p1', 'Pilot', '9');
        """
    )
    conn.commit(); conn.close()

    db = DatabaseManager(str(db_path)); db.close()

    conn = _connect(db_path)
    try:
        assert conn.execute("SELECT missions FROM pilots WHERE id='p1'").fetchone() == (9,)
        assert {row[1]: row[2] for row in conn.execute("PRAGMA table_info(pilots)")}["missions"] == "INTEGER"
    finally:
        conn.close()


def test_check_containing_column_like_text_is_preserved_without_rewrite_confusion(tmp_path):
    db_path = tmp_path / "check_text.sqlite"
    conn = _connect(db_path)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '2.0');
        CREATE TABLE pilots (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE,
            missions TEXT CHECK(note <> 'forbidden missions TEXT text'),
            note TEXT DEFAULT 'missions TEXT should not be rewritten'
        );
        CREATE TABLE missions(id TEXT PRIMARY KEY, pilotId TEXT, enemyContacts TEXT, claimsCount TEXT,
            FOREIGN KEY(pilotId) REFERENCES pilots(id));
        CREATE TABLE squad_members(id TEXT PRIMARY KEY, pilotId TEXT, skill TEXT, morale TEXT, missions TEXT,
            flminutes TEXT, FOREIGN KEY(pilotId) REFERENCES pilots(id));
        INSERT INTO pilots (id, name, missions) VALUES ('p1', 'Pilot', '4');
        """
    )
    conn.commit(); conn.close()

    db = DatabaseManager(str(db_path)); db.close()

    conn = _connect(db_path)
    try:
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='pilots'").fetchone()[0]
        assert "missions INTEGER CHECK(note <> 'forbidden missions TEXT text')" in sql
        assert conn.execute("SELECT missions FROM pilots WHERE id='p1'").fetchone() == (4,)
    finally:
        conn.close()


def test_unsupported_alternative_numeric_type_aborts_before_schema_changes(tmp_path):
    db_path = tmp_path / "unsupported.sqlite"
    conn = _connect(db_path)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '2.0');
        CREATE TABLE pilots (id TEXT PRIMARY KEY, name TEXT UNIQUE, missions NUMERIC);
        CREATE TABLE missions(id TEXT PRIMARY KEY, pilotId TEXT, enemyContacts TEXT, claimsCount TEXT,
            FOREIGN KEY(pilotId) REFERENCES pilots(id));
        CREATE TABLE squad_members(id TEXT PRIMARY KEY, pilotId TEXT, skill TEXT, morale TEXT, missions TEXT,
            flminutes TEXT, FOREIGN KEY(pilotId) REFERENCES pilots(id));
        INSERT INTO pilots (id, name, missions) VALUES ('p1', 'Pilot', '4');
        """
    )
    conn.commit(); conn.close()
    before = _dump(db_path)

    with pytest.raises(ValueError, match="Unsupported numeric column type"):
        DatabaseManager(str(db_path))

    assert _dump(db_path) == before


def test_backup_creation_failure_removes_partial_backup(tmp_path, monkeypatch):
    db_path = tmp_path / "backup_failure.sqlite"
    conn = _connect(db_path)
    _old_schema(conn)
    _seed_valid_rows(conn)
    conn.commit(); conn.close()
    def fail_backup(self, source, dest):
        raise RuntimeError("backup failed")

    monkeypatch.setattr(DatabaseManager, "_run_sqlite_backup", fail_backup)
    with pytest.raises(RuntimeError, match="backup failed"):
        DatabaseManager(str(db_path))

    backup_dir = tmp_path / ".woff-migration-backups"
    assert not list(backup_dir.glob("*.backup.sqlite"))


def test_old_database_without_meta_gets_meta_in_migration_transaction(tmp_path):
    db_path = tmp_path / "no_meta.sqlite"
    conn = _connect(db_path)
    conn.executescript(
        """
        CREATE TABLE pilots (id TEXT PRIMARY KEY, name TEXT UNIQUE, missions TEXT);
        CREATE TABLE missions(id TEXT PRIMARY KEY, pilotId TEXT, enemyContacts TEXT, claimsCount TEXT,
            FOREIGN KEY(pilotId) REFERENCES pilots(id));
        CREATE TABLE squad_members(id TEXT PRIMARY KEY, pilotId TEXT, skill TEXT, morale TEXT, missions TEXT,
            flminutes TEXT, FOREIGN KEY(pilotId) REFERENCES pilots(id));
        INSERT INTO pilots (id, name, missions) VALUES ('p1', 'Pilot', '5');
        """
    )
    conn.commit(); conn.close()

    db = DatabaseManager(str(db_path)); db.close()

    conn = _connect(db_path)
    try:
        assert conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone() == ("3.1",)
        assert conn.execute("SELECT missions FROM pilots WHERE id='p1'").fetchone() == (5,)
    finally:
        conn.close()


def test_restore_holds_exclusive_lock_between_rollback_and_backup(tmp_path, monkeypatch):
    db_path = tmp_path / "restore_lock.sqlite"
    conn = _connect(db_path)
    _old_schema(conn)
    conn.execute("INSERT INTO pilots (id, name, missions) VALUES ('p1', 'Pilot', 'bad')")
    conn.commit(); conn.close()
    before = _dump(db_path)
    original_run = DatabaseManager._run_sqlite_backup
    attempted = []

    def run_backup_and_probe_writer(self, source, dest):
        source_path = source.execute("PRAGMA database_list").fetchone()[2]
        if ".woff-migration-backups" in source_path:
            other = sqlite3.connect(db_path, timeout=0)
            try:
                with pytest.raises(sqlite3.OperationalError, match="locked"):
                    other.execute("INSERT INTO pilots (id, name, missions) VALUES ('p2', 'Writer', '1')")
                attempted.append(True)
            finally:
                other.close()
        return original_run(self, source, dest)

    monkeypatch.setattr(DatabaseManager, "_run_sqlite_backup", run_backup_and_probe_writer)

    with pytest.raises(ValueError, match="Invalid integer values"):
        DatabaseManager(str(db_path))

    assert attempted == [True]
    assert _dump(db_path) == before


def test_sql_comments_in_create_table_are_rejected_before_rebuild(tmp_path):
    db_path = tmp_path / "comments.sqlite"
    conn = _connect(db_path)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '2.0');
        CREATE TABLE pilots (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE,
            -- numeric field from old schema
            missions TEXT
        );
        CREATE TABLE missions(id TEXT PRIMARY KEY, pilotId TEXT, enemyContacts TEXT, claimsCount TEXT,
            FOREIGN KEY(pilotId) REFERENCES pilots(id));
        CREATE TABLE squad_members(id TEXT PRIMARY KEY, pilotId TEXT, skill TEXT, morale TEXT, missions TEXT,
            flminutes TEXT, FOREIGN KEY(pilotId) REFERENCES pilots(id));
        INSERT INTO pilots (id, name, missions) VALUES ('p1', 'Pilot', '5');
        """
    )
    conn.commit(); conn.close()
    before = _dump(db_path)

    with pytest.raises(ValueError, match="SQL comments are not supported"):
        DatabaseManager(str(db_path))

    assert _dump(db_path) == before


def test_escaped_identifier_delimiters_are_rejected_clearly(tmp_path):
    db_path = tmp_path / "escaped_identifier.sqlite"
    conn = _connect(db_path)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '2.0');
        CREATE TABLE pilots (id TEXT PRIMARY KEY, name TEXT UNIQUE, "weird""col" TEXT, missions TEXT);
        CREATE TABLE missions(id TEXT PRIMARY KEY, pilotId TEXT, enemyContacts TEXT, claimsCount TEXT,
            FOREIGN KEY(pilotId) REFERENCES pilots(id));
        CREATE TABLE squad_members(id TEXT PRIMARY KEY, pilotId TEXT, skill TEXT, morale TEXT, missions TEXT,
            flminutes TEXT, FOREIGN KEY(pilotId) REFERENCES pilots(id));
        """
    )
    conn.commit(); conn.close()

    with pytest.raises(ValueError, match="escaped delimiters"):
        DatabaseManager(str(db_path))


def test_backup_dest_connect_failure_removes_reserved_backup_file(tmp_path, monkeypatch):
    db_path = tmp_path / "backup_connect_failure.sqlite"
    conn = _connect(db_path)
    _old_schema(conn)
    _seed_valid_rows(conn)
    conn.commit(); conn.close()
    original_connect = sqlite3.connect

    def fail_backup_dest_connect(path, *args, **kwargs):
        if str(path).endswith(".backup.sqlite"):
            raise RuntimeError("dest open failed")
        return original_connect(path, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", fail_backup_dest_connect)

    with pytest.raises(RuntimeError, match="dest open failed"):
        DatabaseManager(str(db_path))

    backup_dir = tmp_path / ".woff-migration-backups"
    assert not list(backup_dir.glob("*.backup.sqlite"))


def test_restore_backup_failure_keeps_destination_integrity(tmp_path, monkeypatch):
    db_path = tmp_path / "restore_mid_failure.sqlite"
    conn = _connect(db_path)
    _old_schema(conn)
    conn.execute("INSERT INTO pilots (id, name, missions) VALUES ('p1', 'Pilot', 'bad')")
    conn.commit(); conn.close()
    before = _dump(db_path)
    original_run = DatabaseManager._run_sqlite_backup

    def fail_restore_backup(self, source, dest):
        source_path = source.execute("PRAGMA database_list").fetchone()[2]
        if ".woff-migration-backups" in source_path:
            raise RuntimeError("restore backup failed")
        return original_run(self, source, dest)

    monkeypatch.setattr(DatabaseManager, "_run_sqlite_backup", fail_restore_backup)

    with pytest.raises(RuntimeError, match="restore backup failed"):
        DatabaseManager(str(db_path))

    assert _dump(db_path) == before
    conn = _connect(db_path)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        conn.close()
