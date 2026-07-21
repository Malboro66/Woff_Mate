import unittest
import tempfile
import os
import xml.etree.ElementTree as ET

# Sem mais sys.path ou os.path manipulations!
# O pytest (com a ajuda do conftest.py na pasta woff/) resolve os imports automaticamente.
from parsers.xml_parser import WoFFXMLParser
from models import WoFFPilot, WoFFMission, WoFFVictory, WoFFDecoration

# ... (Mocks e resto do código mantêm-se exatamente igual) ...

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
      <Type>Offensive Patrol</Type>
      <Aircraft>SE.5a</Aircraft>
      <Duration>1.5</Duration>
      <Result>Major Engagement</Result>
      <Damage>0</Damage>
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
        self.tmp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".xml", delete=False, encoding="utf-8"
        )
        
    def tearDown(self):
        self.tmp_file.close()
        if os.path.exists(self.tmp_file.name):
            os.unlink(self.tmp_file.name)

    def _write_and_parse(self, content: str) -> bool:
        self.tmp_file.write(content)
        self.tmp_file.flush()
        return self.parser.parse(self.tmp_file.name)

    def test_parse_valid_xml(self):
        ok = self._write_and_parse(MOCK_XML_VALID)
        self.assertTrue(ok)
        self.assertIsNotNone(self.parser.pilot)
        self.assertEqual(len(self.parser.missions), 1)
        self.assertEqual(len(self.parser.victories), 1)
        self.assertEqual(len(self.parser.decorations), 1)

    def test_pilot_data_normalization(self):
        self._write_and_parse(MOCK_XML_VALID)
        p = self.parser.pilot
        
        self.assertIsInstance(p, WoFFPilot)
        self.assertEqual(p.name, "James Percival Hartley")
        self.assertEqual(p.nation, "RFC")
        self.assertEqual(p.status, "Active")
        self.assertEqual(p.startDate, "1917-04-01")
        self.assertTrue(p.id)

    def test_mission_data_normalization(self):
        self._write_and_parse(MOCK_XML_VALID)
        m = self.parser.missions[0]
        
        self.assertIsInstance(m, WoFFMission)
        self.assertEqual(m.date, "1917-04-06")
        self.assertEqual(m.missionType, "Offensive Patrol (OP)")
        self.assertEqual(m.result, "Major Engagement")
        self.assertFalse(m.damageReceived)
        self.assertFalse(m.woundsReceived)

    def test_victory_data_normalization(self):
        self._write_and_parse(MOCK_XML_VALID)
        v = self.parser.victories[0]
        
        self.assertIsInstance(v, WoFFVictory)
        self.assertEqual(v.date, "1917-04-06")
        self.assertEqual(v.time, "10:35")
        self.assertEqual(v.enemyType, "Albatros D.III")
        self.assertEqual(v.victoryType, "Out of Control (OOC)")
        self.assertTrue(v.confirmed)

    def test_decoration_date_normalization(self):
        self._write_and_parse(MOCK_XML_VALID)
        d = self.parser.decorations[0]
        
        self.assertIsInstance(d, WoFFDecoration)
        self.assertEqual(d.name, "Military Cross (MC)")
        self.assertEqual(d.date, "1917-04-15")

    def test_status_kia_normalization(self):
        self._write_and_parse(MOCK_XML_KIA)
        self.assertEqual(self.parser.pilot.status, "KIA")
        self.assertEqual(self.parser.pilot.nation, "American")

    def test_status_severe_wound_normalization(self):
        self._write_and_parse(MOCK_XML_WOUNDED)
        self.assertEqual(self.parser.pilot.status, "Seriously Wounded")
        self.assertEqual(self.parser.pilot.nation, "RNAS")

    def test_parse_invalid_xml(self):
        ok = self._write_and_parse(MOCK_XML_INVALID)
        self.assertFalse(ok)
        self.assertIsNone(self.parser.pilot)

    def test_parse_xml_without_pilot(self):
        ok = self._write_and_parse(MOCK_XML_NO_PILOT)
        self.assertFalse(ok)
        self.assertIsNone(self.parser.pilot)
        self.assertEqual(len(self.parser.missions), 0)

if __name__ == "__main__":
    unittest.main()