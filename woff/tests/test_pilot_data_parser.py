import unittest
import os
import tempfile
from unittest.mock import patch, mock_open


from ..parsers.pilot_data_parser import WoFFPilotDataParser
from ..parsers.xml_parser import WoFFXMLParser
from ..rpg_system import RPGSystem

class TestWoFFPilotDataParser(unittest.TestCase):
    
    def test_parse_log_file(self):
        """Testa parsing de ficheiro de log de missões."""
        # A primeira linha é o contador de registos (ignorada pelo parser)
        # O parser precisa de pelo menos 14 colunas (índice 13 = Esquadrão)
        mock_content = "1\n"
        mock_content += "6;4;1917;10;30;Arras;Filescamp;OP;SE.5a;;45;100;SE.5a;No. 56 Sqn RFC;troops;Army Camp;N50*17;E2*42;;; Final Status: Landed safely.;\n"
        
        parser = WoFFPilotDataParser()
        with patch("builtins.open", mock_open(read_data=mock_content)):
            ok = parser.parse("Pilot1Log.txt")
        
        self.assertTrue(ok)
        self.assertEqual(len(parser.missions), 1)
        
        m = parser.missions[0]
        self.assertEqual(m.date, "1917-04-06")
        self.assertEqual(m.time, "10:30")  # Testa a extração da hora!
        self.assertEqual(m.sector, "Arras")
        self.assertEqual(m.aircraft, "SE.5a")
        self.assertEqual(m.squadron, "No. 56 Sqn RFC")
    

    def test_parse_log_populates_wounds_and_damage_flags(self):
        """PilotLog.txt deve popular explicitamente dano e ferimentos."""
        mock_content = "2\n"
        mock_content += "6;4;1917;10;30;Arras;Filescamp;OP;SE.5a;;45;100;SE.5a;No. 56 Sqn RFC;troops;Army Camp;N50*17;E2*42;Damaged;Wounded; Final Status: Crash landed wounded.;\n"
        mock_content += "7;4;1917;11;00;Arras;Filescamp;OP;SE.5a;;45;100;SE.5a;No. 56 Sqn RFC;troops;Army Camp;N50*17;E2*42;No;0; Final Status: Landed safely.;\n"

        parser = WoFFPilotDataParser()
        with patch("builtins.open", mock_open(read_data=mock_content)):
            ok = parser.parse("Pilot1Log.txt")

        self.assertTrue(ok)
        self.assertEqual(len(parser.missions), 2)
        self.assertTrue(parser.missions[0].damageReceived)
        self.assertTrue(parser.missions[0].woundsReceived)
        self.assertFalse(parser.missions[1].damageReceived)
        self.assertFalse(parser.missions[1].woundsReceived)

    def test_parse_log_damage_wounds_match_xml_boolean_semantics(self):
        """TXT e XML devem produzir os mesmos booleanos para missão equivalente."""
        mock_content = "1\n"
        mock_content += "6;4;1917;10;30;Arras;Filescamp;OP;SE.5a;;45;100;SE.5a;No. 56 Sqn RFC;troops;Army Camp;N50*17;E2*42;Yes;1; Final Status: Returned damaged and wounded.;\n"

        txt_parser = WoFFPilotDataParser()
        with patch("builtins.open", mock_open(read_data=mock_content)):
            self.assertTrue(txt_parser.parse("Pilot1Log.txt"))

        xml = """<?xml version="1.0" encoding="UTF-8"?>
<Campaign>
  <Pilot><PilotName>Test Pilot</PilotName><Status>Active</Status></Pilot>
  <Missions>
    <Mission>
      <Date>1917-04-06</Date><Time>10:30</Time><Type>OP</Type>
      <Aircraft>SE.5a</Aircraft><Damage>Yes</Damage><Wounds>1</Wounds>
    </Mission>
  </Missions>
</Campaign>
"""
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(xml)
            xml_path = f.name
        try:
            xml_parser = WoFFXMLParser()
            self.assertTrue(xml_parser.parse(xml_path))
        finally:
            os.unlink(xml_path)

        self.assertEqual(
            txt_parser.missions[0].damageReceived,
            xml_parser.missions[0].damageReceived,
        )
        self.assertEqual(
            txt_parser.missions[0].woundsReceived,
            xml_parser.missions[0].woundsReceived,
        )

    def test_parse_log_flags_feed_fatigue_calculation(self):
        """Ferimento e dano vindos do TXT devem impactar fadiga downstream."""
        mock_content = "1\n"
        mock_content += "6;4;1917;10;30;Arras;Filescamp;OP;SE.5a;;45;100;SE.5a;No. 56 Sqn RFC;troops;Army Camp;N50*17;E2*42;1;Wounded; Final Status: Crash landed wounded.;\n"

        parser = WoFFPilotDataParser()
        with patch("builtins.open", mock_open(read_data=mock_content)):
            self.assertTrue(parser.parse("Pilot1Log.txt"))

        mission = parser.missions[0]
        rpg = RPGSystem()
        with patch("woff.rpg_system.random") as mock_random:
            mock_random.random.return_value = 1.0
            fatigue = rpg.calculate_fatigue([mission.__dict__])

        self.assertEqual(fatigue, 30)

    def test_parse_claims_file(self):
        """Testa parsing de ficheiro de vitórias (Claims) e confirmação."""
        # Usar 2 registos para testar vitória confirmada e não confirmada
        mock_content = "2\n"
        # 1: Destruído em chamas (não contém "confirmed" -> False)
        mock_content += "6;4;1917;10;30;Arras;Filescamp;OP;SE.5a;1;Albatros D.III;Destroyed in flames;Albatros\n"
        # 2: Forçado a aterrar (contém "Confirmed" -> True)
        mock_content += "7;4;1917;12;00;Arras;Filescamp;OP;SE.5a;1;DFW C.V;Forced to land Confirmed;DFW\n"
        
        parser = WoFFPilotDataParser()
        with patch("builtins.open", mock_open(read_data=mock_content)):
            ok = parser.parse("Pilot1Claims.txt")
            
        self.assertTrue(ok)
        self.assertEqual(len(parser.victories), 2)
        
        # Vitória 1 (Não confirmada)
        v1 = parser.victories[0]
        self.assertEqual(v1.date, "1917-04-06")
        self.assertEqual(v1.time, "10:30")
        self.assertEqual(v1.enemyType, "Albatros D.III")
        self.assertEqual(v1.victoryType, "Destroyed — In Flames") # Normalizado pelo maps.py
        # FIX: "Destroyed in flames" não contém a palavra "confirmed"
        self.assertFalse(v1.confirmed) 
        
        # Vitória 2 (Confirmada)
        v2 = parser.victories[1]
        self.assertEqual(v2.date, "1917-04-07")
        self.assertEqual(v2.time, "12:00")
        self.assertEqual(v2.enemyType, "DFW C.V")
        self.assertEqual(v2.victoryType, "Forced to Land") # Normalizado
        self.assertTrue(v2.confirmed) # Contém "Confirmed"
    
    def test_parse_squads_file(self):
        """Testa parsing de histórico de esquadrões."""
        # Sem cabeçalho, o parser lê a última linha
        mock_content = "6;4;1917;10;30;Flanders;Filescamp;No. 56 Sqn RFC;SE.5a;SE.5a;Enlisted, based at Filescamp, rank: Captain.;No. 56 Squadron\n"
        
        parser = WoFFPilotDataParser()
        with patch("builtins.open", mock_open(read_data=mock_content)):
            ok = parser.parse("Pilot1Squads.txt")
            
        self.assertTrue(ok)
        self.assertIsNotNone(parser.pilot)
        
        # Type narrowing para o Pyright compreender que não é None
        assert parser.pilot is not None
        p = parser.pilot
        
        self.assertEqual(p.squadron, "No. 56 Sqn RFC")
        self.assertEqual(p.aircraft, "SE.5a")
        self.assertEqual(p.aerodrome, "Filescamp")
        self.assertEqual(p.sector, "Flanders")
        # Testa a extração da patente via Regex na coluna 10
        self.assertEqual(p.rank, "Captain")
    
    def test_pilot_id_placeholder(self):
        """Testa que pilot.name é um placeholder ('Pilot 1') antes do Dossier ser lido."""
        mock_content = "1\n6;4;1917;10;30;Arras;Filescamp;OP;SE.5a;;45;100;SE.5a;No. 56 Sqn RFC;\n"
        
        parser = WoFFPilotDataParser()
        with patch("builtins.open", mock_open(read_data=mock_content)):
            parser.parse("Pilot1Log.txt")
            
        self.assertIsNotNone(parser.pilot)
        
        # Type narrowing para o Pyright compreender que não é None
        assert parser.pilot is not None
        
        # O parser extrai o ID do nome do ficheiro e formata como "Pilot 1"
        self.assertEqual(parser.pilot.name, "Pilot 1")
        # O database.py deverá resolver este "Pilot 1" para o UUID real usando GLOB no source_file

if __name__ == "__main__":
    unittest.main()
