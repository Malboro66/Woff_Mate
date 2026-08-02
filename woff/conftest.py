# woff/conftest.py
import os


import pytest
import tempfile

from .database import DatabaseManager
from .campaign_engine import CampaignEngine
from .models import WoFFPilot, WoFFMission

@pytest.fixture
def db_manager():
    """Cria uma Base de Dados SQLite temporária para testes."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db = DatabaseManager(tmp.name)
    
    yield db
    
    db = None
    if os.path.exists(tmp.name):
        os.unlink(tmp.name)
    for ext in ["-wal", "-shm"]:
        path = tmp.name + ext
        if os.path.exists(path):
            os.unlink(path)

@pytest.fixture
def campaign_engine(db_manager):
    """Instancia o CampaignEngine com a DB temporária."""
    return CampaignEngine(db_manager)

@pytest.fixture
def test_pilot():
    """Cria um objeto WoFFPilot padrão para testes."""
    return WoFFPilot(name="Test Pilot", squadron="Test Sqn", rank="Captain")

@pytest.fixture
def test_mission(test_pilot):
    """Cria um objeto WoFFMission padrão associado ao piloto de teste."""
    return WoFFMission(
        id="M_TEST", 
        pilotId=test_pilot.id, 
        date="1917-04-06", 
        time="10:30", 
        missionType="OP"
    )
