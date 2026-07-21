import unittest
import sys
import os
from unittest.mock import patch, mock_open

# Adicionar a pasta woff ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from parsers.pilot_data_parser import WoFFPilotDataParser

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
    
    def test_parse_claims_file(self):
        """Testa parsing de ficheiro de vitórias (Claims)."""
        # Primeira linha = contador, segunda linha = dados (precisa de >= 12 colunas)
        mock_content = "1\n"
        mock_content += "6;4;1917;10;30;Arras;Filescamp;OP;SE.5a;1;Albatros D.III;Destroyed;Albatros\n"
        
        parser = WoFFPilotDataParser()
        with patch("builtins.open", mock_open(read_data=mock_content)):
            ok = parser.parse("Pilot1Claims.txt")
            
        self.assertTrue(ok)
        self.assertEqual(len(parser.victories), 1)
        
        v = parser.victories[0]
        self.assertEqual(v.date, "1917-04-06")
        self.assertEqual(v.time, "10:30")
        self.assertEqual(v.enemyType, "Albatros D.III")
        self.assertEqual(v.victoryType, "Destroyed — In Flames") # Normalizado pelo maps.py
        self.assertTrue(v.confirmed) # Contém "Destroyed", logo é confirmado
    
    def test_parse_squads_file(self):
        """Testa parsing de histórico de esquadrões."""
        # Sem cabeçalho, o parser lê a última linha
        mock_content = "6;4;1917;10;30;Flanders;Filescamp;No. 56 Sqn RFC;SE.5a;SE.5a;Enlisted, based at Filescamp, rank: Captain.;No. 56 Squadron\n"
        
        parser = WoFFPilotDataParser()
        with patch("builtins.open", mock_open(read_data=mock_content)):
            ok = parser.parse("Pilot1Squads.txt")
            
        self.assertTrue(ok)
        self.assertIsNotNone(parser.pilot)
        
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
            
        # O parser extrai o ID do nome do ficheiro e formata como "Pilot 1"
        self.assertEqual(parser.pilot.name, "Pilot 1")
        # O database.py deverá resolver este "Pilot 1" para o UUID real usando GLOB no source_file

if __name__ == "__main__":
    unittest.main()