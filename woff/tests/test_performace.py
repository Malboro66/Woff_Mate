import unittest
import tempfile
import os
import time
from typing import Any
from unittest.mock import patch, mock_open


from ..parsers.dossier_parser import WoFFDossierParser
from ..database import DatabaseManager
from ..models import WoFFPilot, WoFFMission

def _generate_large_encoded_dossier(filename: str, num_lines: int = 50000) -> bytes:
    """Gera um ficheiro Dossier ofuscado gigante para testes de stress."""
    pName = filename.replace(".txt", "")
    plainkey = "78CrztPRVzYQpYu90MnyW"
    soucet = sum(ord(c) for c in pName)
    sum_val = soucet % 128
    pos = sum_val % 10 or 9
    length = sum_val % 12 or 4
    prekey = "".join(plainkey[i - 1] for i in range(pos, pos + length))
    postkey = "".join(plainkey[i - 1] for i in range(length, length + pos))
    sp = chr(sum_val)
    key = prekey + sp + plainkey + postkey

    raw_data = bytearray()
    current_key = key

    for i in range(num_lines):
        # Simular uma string de dados em cada linha
        line = f"Line_{i}_data_string_for_testing_performance_and_memory_usage"
        key_index = 0
        counter = 0x80
        
        for char in line:
            val = ord(char)
            k_char = ord(current_key[key_index])
            xor_val = val ^ k_char
            raw_data.extend(f"{xor_val:02X}".encode('ascii'))
            raw_data.append(counter)
            counter = 0x80 + ((counter - 0x80 + 1) % 128)
            key_index = (key_index + 1) % len(current_key)
            
        raw_data.extend(b"\r\n")
        current_key = current_key[::-1]
        
    return bytes(raw_data)


class TestPerformance(unittest.TestCase):
    
    # FIX: Anotações de tipo para o Pyright não se queixar do None no tearDown
    db: DatabaseManager
    tmp_db: Any
    
    @classmethod
    def setUpClass(cls):
        import logging
        logging.disable(logging.CRITICAL)

    @classmethod
    def tearDownClass(cls):
        import logging
        logging.disable(logging.NOTSET)

    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        self.db = DatabaseManager(self.tmp_db.name)

    def tearDown(self):
        # FIX: Ignorar o erro de tipo ao atribuir None, pois é intencional para o GC
        self.db = None  # type: ignore[assignment]
        if os.path.exists(self.tmp_db.name):
            os.unlink(self.tmp_db.name)

    def test_parse_large_dossier(self):
        """Testa parsing de um dossier binário gigante (simula 50.000 linhas)."""
        filename = "Pilot1Dossier.txt"
        # Gerar ~5MB de dados ofuscados
        large_mock_data = _generate_large_encoded_dossier(filename, 50000)
        
        parser = WoFFDossierParser()
        
        start_time = time.time()
        
        with patch("builtins.open", mock_open(read_data=large_mock_data)):
            ok = parser.parse(filename)
            
        elapsed = time.time() - start_time
        
        self.assertTrue(ok)
        # FIX: Limite generoso para evitar flaky test em hardware variável
        self.assertLess(elapsed, 5.0, f"Parsing demorou {elapsed:.2f}s, esperado < 5.0s")
        print(f"\n  [Perf] Parse Dossier (50k linhas): {elapsed:.3f}s")

    def test_database_merge_1000_missions(self):
        """Testa inserção em massa de 1000 missões numa única transação."""
        pilot = WoFFPilot(name="Stress Test Pilot")
        self.db.merge_and_write(pilot, [], [], [])
        
        # Criar 1000 missões únicas (variam a hora para não colidir na UNIQUE constraint)
        missions = [
            WoFFMission(
                pilotId=pilot.id,
                date="1917-04-06",
                time=f"{10 + i//60:02d}:{i%60:02d}", # 10:00 a 26:39
                missionType="OP",
                aircraft="SE.5a"
            ) for i in range(1000)
        ]
        
        start_time = time.time()
        ok = self.db.merge_and_write(None, missions, [], [])
        elapsed = time.time() - start_time
        
        self.assertTrue(ok)
        # SQLite com WAL deve inserir 1000 linhas em frações de segundo
        self.assertLess(elapsed, 2.0, f"Merge de 1000 missões demorou {elapsed:.2f}s, esperado < 2.0s")
        print(f"\n  [Perf] DB Merge 1000 missões: {elapsed:.3f}s")
        
        # Validar que todas foram inseridas
        import sqlite3
        conn = sqlite3.connect(self.tmp_db.name)
        cursor = conn.execute("SELECT COUNT(*) FROM missions WHERE pilotId = ?", (pilot.id,))
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 1000)

    def test_memory_usage(self):
        """Monitora uso de memória durante operações pesadas (requer psutil)."""
        try:
            import psutil
        except ImportError:
            self.skipTest("psutil não instalado. Instale com 'pip install psutil' para correr este teste.")
            
        process = psutil.Process(os.getpid())
        before = process.memory_info().rss
        
        # Operação pesada: Gerar e fazer parse de um ficheiro grande
        large_mock_data = _generate_large_encoded_dossier("Pilot1Dossier.txt", 20000)
        parser = WoFFDossierParser()
        with patch("builtins.open", mock_open(read_data=large_mock_data)):
            parser.parse("Pilot1Dossier.txt")
            
        after = process.memory_info().rss
        diff_mb = (after - before) / (1024 * 1024)
        
        # O aumento de memória não deve exceder 50MB (Python tem overhead, mas não deve vazar)
        self.assertLess(diff_mb, 50.0, f"Aumento de memória foi {diff_mb:.2f}MB, esperado < 50MB")
        print(f"\n  [Perf] Aumento de memória (20k linhas): {diff_mb:.2f} MB")

if __name__ == "__main__":
    unittest.main()
