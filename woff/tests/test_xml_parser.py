import unittest
import tempfile
import os
import xml.etree.ElementTree as ET

# Sem mais sys.path ou os.path manipulations!
# O pytest (com a ajuda do conftest.py na pasta woff/) resolve os imports automaticamente.
from parsers.xml_parser import WoFFXMLParser
from models import WoFFPilot, WoFFMission, WoFFVictory, WoFFDecoration


# ──────────────────────────────────────────────────────────────
# MOCK DATA
# ──────────────────────────────────────────────────────────────

MOCK_XML_VALID = """<?xml version="1.0" encoding="UTF-8"?>
<Campaign>
  <Pilot>
    <PilotName>James Percival Hartley</PilotName>
    <Nation>RFC</Nation>
    <Rank>Captain</Rank>
    <Squadron>No. 56 Squadron RFC</Squadron>
    <Aircraft>SE.5a</Aircraft>
    <Aerodrome>Filescamp Farm</Aerodrome>
    <Sector>Arras</Sector>
    <StartDate>1917-04-01</StartDate>
    <Status>Active</Status>
    <Notes>Transferred from No. 60 Sqn.</Notes>
  </Pilot>
  <Missions>
    <Mission>
      <Date>1917-04-06</Date>
      <Time>10:30</Time>
      <Type>Offensive Patrol</Type>
      <Aircraft>SE.5a</Aircraft>
      <Duration>1.5</Duration>
      <Result>Major Engagement</Result>
      <Damage>0</Damage>
      <Wounds>0</Wounds>
    </Mission>
    <!-- Missão Duplicada (Mesma data/hora/tipo/avião) -->
    <Mission>
      <Date>1917-04-06</Date>
      <Time>10:30</Time>
      <Type>Offensive Patrol</Type>
      <Aircraft>SE.5a</Aircraft>
      <Duration>1.5</Duration>
      <Result>Major Engagement</Result>
    </Mission>
    <Mission>
      <Date>1917-04-09</Date>
      <Time>14:00</Time>
      <Type>Artillery Observation</Type>
      <Aircraft>SE.5a</Aircraft>
      <Duration>2.0</Duration>
      <Result>Aircraft Damaged (Returned)</Result>
      <Damage>1</Damage>
      <Wounds>0</Wounds>
    </Mission>
  </Missions>
  <Victories>
    <Victory>
      <Date>1917-04-06</Date>
      <Time>10:35</Time>
      <EnemyType>Albatros D.III</EnemyType>
      <Type>Out of Control</Type>
      <Confirmed>true</Confirmed>
    </Victory>
    <Victory>
      <Date>1917-04-06</Date>
      <Time>10:42</Time>
      <EnemyType>Albatros D.III</EnemyType>
      <Type>Destroyed</Type>
      <Confirmed>true</Confirmed>
    </Victory>
  </Victories>
  <Decorations>
    <Decoration>
      <Name>Military Cross (MC)</Name>
      <Date>April 15, 1917</Date>
    </Decoration>
  </Decorations>
</Campaign>
"""

MOCK_XML_KIA = """<?xml version="1.0" encoding="UTF-8"?>
<Campaign>
  <Pilot>
    <PilotName>John Doe</PilotName>
    <Nation>USAS</Nation>
    <Status>Killed in Action</Status>
  </Pilot>
</Campaign>
"""

MOCK_XML_WOUNDED = """<?xml version="1.0" encoding="UTF-8"?>
<Campaign>
  <Pilot>
    <PilotName>Jane Smith</PilotName>
    <Nation>RNAS</Nation>
    <Status>In Hospital</Status>
    <WoundSeverity>Serious</WoundSeverity>
  </Pilot>
</Campaign>
"""

MOCK_XML_INVALID = """<?xml version="1.0" encoding="UTF-8"?>
<Campaign>
  <Pilot>
    <Name>Missing closing tag
</Campaign>
"""

MOCK_XML_NO_PILOT = """<?xml version="1.0" encoding="UTF-8"?>
<Campaign>
  <Missions>
    <Mission><Date>1917-01-01</Date></Mission>
  </Missions>
</Campaign>
"""


class TestWoFFXMLParser(unittest.TestCase):

    def setUp(self):
        self.parser = WoFFXMLParser()
        # Cria um ficheiro temporário para os testes
        self.tmp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".xml", delete=False, encoding="utf-8"
        )
        
    def tearDown(self):
        # Fecha e apaga o ficheiro temporário após cada teste
        self.tmp_file.close()
        if os.path.exists(self.tmp_file.name):
            os.unlink(self.tmp_file.name)

    def _write_and_parse(self, content: str) -> bool:
        """Helper: Escreve no ficheiro temp e corre o parser."""
        self.tmp_file.write(content)
        self.tmp_file.flush() # Garante que o conteúdo é escrito no disco
        return self.parser.parse(self.tmp_file.name)

    # ── Testes de Sucesso ──

    def test_parse_valid_xml(self):
        """Testa se um XML bem formado retorna True e popula os dados."""
        ok = self._write_and_parse(MOCK_XML_VALID)
        self.assertTrue(ok)
        self.assertIsNotNone(self.parser.pilot)
        self.assertEqual(len(self.parser.missions), 3)
        self.assertEqual(len(self.parser.victories), 2)
        self.assertEqual(len(self.parser.decorations), 1)

    def test_pilot_data_normalization(self):
        """Testa se os dados do piloto são normalizados corretamente."""
        self._write_and_parse(MOCK_XML_VALID)
        p = self.parser.pilot
        
        # FIX: Type narrowing para o Pyright compreender que não é None
        self.assertIsNotNone(p)
        assert p is not None
        
        self.assertIsInstance(p, WoFFPilot)
        self.assertEqual(p.name, "James Percival Hartley")
        self.assertEqual(p.nation, "RFC")
        self.assertEqual(p.status, "Active")
        self.assertEqual(p.startDate, "1917-04-01") # Já estava normalizado
        self.assertTrue(p.id) # Tem de ter um ID gerado

    def test_mission_data_normalization(self):
        """Testa a extração e normalização da missão."""
        self._write_and_parse(MOCK_XML_VALID)
        # Testamos a primeira missão do Mock
        m = self.parser.missions[0]
        
        self.assertIsInstance(m, WoFFMission)
        self.assertEqual(m.date, "1917-04-06")
        self.assertEqual(m.time, "10:30")
        self.assertEqual(m.missionType, "Offensive Patrol (OP)") # Normalizado
        self.assertEqual(m.result, "Major Engagement")
        self.assertFalse(m.damageReceived)
        self.assertFalse(m.woundsReceived)

    def test_victory_data_normalization(self):
        """Testa a extração e normalização da vitória."""
        self._write_and_parse(MOCK_XML_VALID)
        # Testamos a primeira vitória do Mock
        v = self.parser.victories[0]
        
        self.assertIsInstance(v, WoFFVictory)
        self.assertEqual(v.date, "1917-04-06")
        self.assertEqual(v.time, "10:35")
        self.assertEqual(v.enemyType, "Albatros D.III")
        self.assertEqual(v.victoryType, "Out of Control (OOC)") # Normalizado
        self.assertTrue(v.confirmed)

    def test_decoration_date_normalization(self):
        """Testa se a data da condecoração é normalizada para ISO 8601."""
        self._write_and_parse(MOCK_XML_VALID)
        d = self.parser.decorations[0]
        
        self.assertIsInstance(d, WoFFDecoration)
        self.assertEqual(d.name, "Military Cross (MC)")
        self.assertEqual(d.date, "1917-04-15") # Normalizado de "April 15, 1917"

    # ── Testes de Normalização de Status ──

    def test_status_kia_normalization(self):
        """Testa se 'Killed in Action' vira 'KIA'."""
        self._write_and_parse(MOCK_XML_KIA)
        
        # FIX: Type narrowing para o Pyright compreender que não é None
        self.assertIsNotNone(self.parser.pilot)
        assert self.parser.pilot is not None
        
        self.assertEqual(self.parser.pilot.status, "KIA")
        self.assertEqual(self.parser.pilot.nation, "American")

    def test_status_severe_wound_normalization(self):
        """Testa se 'In Hospital' + 'Serious' vira 'Seriously Wounded'."""
        self._write_and_parse(MOCK_XML_WOUNDED)
        
        # FIX: Type narrowing para o Pyright compreender que não é None
        self.assertIsNotNone(self.parser.pilot)
        assert self.parser.pilot is not None
        
        self.assertEqual(self.parser.pilot.status, "Seriously Wounded")
        self.assertEqual(self.parser.pilot.nation, "RNAS")

    # ── Testes de Falha / Edge Cases ──

    def test_parse_invalid_xml(self):
        """Testa se um XML corrompido retorna False e loga o erro."""
        ok = self._write_and_parse(MOCK_XML_INVALID)
        self.assertFalse(ok)
        self.assertIsNone(self.parser.pilot)

    def test_parse_xml_without_pilot(self):
        """Testa se um XML sem a tag PilotName retorna False (sem fallback para nome do ficheiro)."""
        ok = self._write_and_parse(MOCK_XML_NO_PILOT)
        # FIX: O parser agora deve rejeitar XMLs sem PilotName para evitar pilotos fantasmas
        self.assertFalse(ok)
        self.assertIsNone(self.parser.pilot)
        self.assertEqual(len(self.parser.missions), 0)
        
    def test_parse_multiple_missions_victories(self):
        """Testa extração de múltiplas missões e vitórias (incluindo duplicadas no XML)."""
        ok = self._write_and_parse(MOCK_XML_VALID)
        self.assertTrue(ok)
        
        # O Parser deve extrair TODOS os elementos do XML (3 missões, 2 vitórias)
        # A deduplicação será responsabilidade do DatabaseManager
        self.assertEqual(len(self.parser.missions), 3)
        self.assertEqual(len(self.parser.victories), 2)
        self.assertEqual(len(self.parser.decorations), 1)
        
        # Verifica se a segunda missão foi lida corretamente (a duplicada)
        m2 = self.parser.missions[1]
        self.assertEqual(m2.date, "1917-04-06")
        self.assertEqual(m2.time, "10:30") # Hora extraída
        
        # Verifica a terceira missão (única)
        m3 = self.parser.missions[2]
        self.assertEqual(m3.date, "1917-04-09")
        self.assertEqual(m3.missionType, "Artillery Observation (Art.Obs.)")


if __name__ == "__main__":
    unittest.main()