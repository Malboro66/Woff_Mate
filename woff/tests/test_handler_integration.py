import unittest
import tempfile
import threading
import os
import shutil
from unittest.mock import patch, MagicMock


from ..config import WatchdogConfig
from ..database import DatabaseManager
from ..campaign_engine import CampaignEngine
from ..handler import WoFFEventHandler

# Mock de um ficheiro de campanha XML válido
MOCK_XML_VALID = """<?xml version="1.0" encoding="UTF-8"?>
<Campaign>
  <Pilot>
    <PilotName>James Percival Hartley</PilotName>
    <Nation>RFC</Nation>
    <Rank>Captain</Rank>
    <Squadron>No. 56 Squadron RFC</Squadron>
    <Aircraft>SE.5a</Aircraft>
    <Status>Active</Status>
  </Pilot>
</Campaign>
"""

class TestHandlerIntegration(unittest.TestCase):
    """Testa o handler com ficheiros reais temporários."""
    
    @classmethod
    def setUpClass(cls):
        # Desativar logs durante os testes para não poluir o terminal
        import logging
        logging.disable(logging.CRITICAL)

    @classmethod
    def tearDownClass(cls):
        import logging
        logging.disable(logging.NOTSET)

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test.db")
        self.db = DatabaseManager(self.db_path)
        self.engine = CampaignEngine(self.db)
        
        self.config = WatchdogConfig(
            watch_paths=[self.tmp_dir],
            stability_timeout_sec=1.0, # Reduzir timeout para testes rápidos
            stability_check_interval_sec=0.05
        )
        
        self.handler = WoFFEventHandler(
            config=self.config,
            db_manager=self.db,
            campaign_engine=self.engine
        )
    
    def tearDown(self):
        # Limpar pasta temporária e DB
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)
    
    def test_file_modified_event(self):
        """Simula evento de modificação e verifica processamento assíncrono determinístico."""
        xml_path = os.path.join(self.tmp_dir, "campaign.xml")

        # Escrever ficheiro real no disco
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(MOCK_XML_VALID)

        from watchdog.events import FileModifiedEvent
        event = FileModifiedEvent(xml_path)

        # FIX: Mockar o pool para executar sincronamente, evitando race conditions
        # e eliminando a necessidade de aceder a _process (atributo privado).
        original_pool = self.handler._pool
        self.handler._pool = MagicMock()

        def sync_submit(fn, *args, **kwargs):
            """Executa a tarefa imediatamente no thread principal."""
            fn(*args, **kwargs)
            return MagicMock()  # Future-like object

        self.handler._pool.submit = sync_submit

        try:
            # Disparar evento — o processamento corre sincronamente
            self.handler.on_modified(event)

            # Verificar se chegou à Base de Dados
            status, rank = self.db.get_pilot_state("James Percival Hartley")
            self.assertIsNotNone(status)
            self.assertEqual(status, "Active")
        finally:
            self.handler._pool = original_pool

    def test_inflight_debounce(self):
        """Testa que eventos rápidos duplicados são ignorados pelo set _inflight."""
        xml_path = os.path.join(self.tmp_dir, "campaign.xml")
        
        # Escrever ficheiro real no disco
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(MOCK_XML_VALID)
            
        from watchdog.events import FileModifiedEvent
        event = FileModifiedEvent(xml_path)
        
        # Fazer Mock do submit para não executar o processamento real,
        # permitindo-nos contar apenas quantas vezes foi chamado.
        self.handler._pool = MagicMock()
        
        # Disparar 5 eventos idênticos imediatamente
        self.handler.on_modified(event)
        self.handler.on_modified(event)
        self.handler.on_modified(event)
        self.handler.on_modified(event)
        self.handler.on_modified(event)
        
        # O _inflight set deve ter bloqueado os 4 últimos eventos
        # O submit só deve ter sido chamado 1 vez
        self.assertEqual(self.handler._pool.submit.call_count, 1)
        
        # Simular o final do processamento (limpar _inflight)
        with self.handler._inflight_lock:
            self.handler._inflight.discard(xml_path)
            
        # Disparar outro evento, agora já deve ser aceite novamente
        self.handler.on_modified(event)
        self.assertEqual(self.handler._pool.submit.call_count, 2)

if __name__ == "__main__":
    unittest.main()
