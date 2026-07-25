import unittest
import sys
import os

# Adicionar a pasta woff ao path (caso o conftest.py não esteja configurado)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from rpg_system import RPGSystem

class TestRPGSystem(unittest.TestCase):
    
    def setUp(self):
        self.rpg = RPGSystem()
    
    def test_fatigue_single_mission(self):
        """Testa fadiga de uma missão normal nos últimos 3 dias."""
        missions = [{"date": "1917-04-06", "woundsReceived": False, "damageReceived": False}]
        # 15 (base) + 0 (ferido) + 0 (danos) = 15
        self.assertEqual(self.rpg.calculate_fatigue(missions), 15)
    
    def test_fatigue_wounded(self):
        """Testa que ferimentos aumentam a fadiga."""
        missions = [{"date": "1917-04-06", "woundsReceived": True, "damageReceived": False}]
        # 25 (base ferido) + 0 (danos) = 25
        self.assertEqual(self.rpg.calculate_fatigue(missions), 25)
        
    def test_fatigue_damaged(self):
        """Testa que danos na aeronave aumentam a fadiga."""
        missions = [{"date": "1917-04-06", "woundsReceived": False, "damageReceived": True}]
        # 15 (base) + 5 (danos) = 20
        self.assertEqual(self.rpg.calculate_fatigue(missions), 20)

    def test_fatigue_old_mission_ignored(self):
        """Testa que missões antigas (>3 dias) não geram fadiga."""
        # FIX: Adicionar uma missão recente para servir de âncora (hoje)
        missions = [
            {"date": "1917-04-06", "woundsReceived": False, "damageReceived": False},  # Hoje
            {"date": "1917-01-01", "woundsReceived": False, "damageReceived": False},  # Antiga
        ]
        # Só a de 06-04 conta (15). A de Janeiro está fora da janela de 3 dias.
        self.assertEqual(self.rpg.calculate_fatigue(missions), 15)
    
    def test_morale_victory_boost(self):
        """Testa que vitórias aumentam a moral."""
        missions = [{"claimsCount": "2", "woundsReceived": False, "damageReceived": False}]
        # 75 (base) + 5 (vitória) = 80
        self.assertEqual(self.rpg.calculate_morale(missions, "Active"), 80)
    
    def test_morale_wounded_penalty(self):
        """Testa que ferimentos baixam a moral."""
        missions = [{"claimsCount": "0", "woundsReceived": True, "damageReceived": False}]
        # 75 (base) - 10 (ferido) = 65
        self.assertEqual(self.rpg.calculate_morale(missions, "Active"), 65)
        
    def test_morale_damaged_penalty(self):
        """Testa que danos baixam a moral."""
        missions = [{"claimsCount": "0", "woundsReceived": False, "damageReceived": True}]
        # 75 (base) - 3 (danos) = 72
        self.assertEqual(self.rpg.calculate_morale(missions, "Active"), 72)

    def test_morale_hospital_status_penalty(self):
        """Testa que estar no hospital baixa a moral."""
        missions = [{"claimsCount": "0", "woundsReceived": False, "damageReceived": False}]
        # 75 (base) - 20 (status hospital) = 55
        self.assertEqual(self.rpg.calculate_morale(missions, "Wounded"), 55)
    
    def test_stress_combat_contacts(self):
        """Testa cálculo de stress baseado em contactos inimigos."""
        missions = [{"enemyContacts": "3", "result": ""}]
        # 3 contactos * 4 = 12
        self.assertEqual(self.rpg.calculate_stress(missions), 12)
        
    def test_stress_forced_landing(self):
        """Testa que aterragens forçadas aumentam o stress."""
        missions = [{"enemyContacts": "0", "result": "Forced Landing"}]
        # 0 contactos + 20 (forçada) = 20
        self.assertEqual(self.rpg.calculate_stress(missions), 20)

if __name__ == "__main__":
    unittest.main()