import unittest
import random
from unittest.mock import Mock


from ..rpg_system import RPGSystem

class TestRPGSystem(unittest.TestCase):
    
    def setUp(self):
        self.rng = Mock()
        self.rng.random.return_value = 1.0
        self.rpg = RPGSystem(rng=self.rng)

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
        missions = [
            {"date": "1917-04-06", "woundsReceived": False, "damageReceived": False},  # Hoje
            {"date": "1917-01-01", "woundsReceived": False, "damageReceived": False},  # Antiga
        ]
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

    def test_morale_uses_ten_most_recent_missions_from_descending_history(self):
        """Garante que a moral ignora a 11ª missão, que é a mais antiga no histórico."""
        missions = [
            {"claimsCount": "1", "woundsReceived": False, "damageReceived": False}
            for _ in range(10)
        ]
        missions.append(
            {"claimsCount": "0", "woundsReceived": True, "damageReceived": False}
        )

        # 75 base + 10 vitórias recentes * 5. A penalização da 11ª missão
        # antiga não deve ser considerada.
        self.assertEqual(self.rpg.calculate_morale(missions, "Active"), 100)
    
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

    def test_fatigue_random_events_are_controllable(self):
        missions = [{"date": "1917-04-06"}]
        rested = Mock(random=Mock(return_value=0.04))
        insomnia = Mock(random=Mock(return_value=0.08))

        self.assertEqual(RPGSystem(rng=rested).calculate_fatigue(missions), 5)
        self.assertEqual(RPGSystem(rng=insomnia).calculate_fatigue(missions), 30)

    def test_morale_random_event_is_controllable(self):
        rng = Mock()
        rng.random.return_value = 0.10
        rng.randint.return_value = -7

        self.assertEqual(RPGSystem(rng=rng).calculate_morale([], "Active"), 68)
        rng.randint.assert_called_once_with(-10, 10)

    def test_stress_random_event_is_controllable(self):
        rng = Mock(random=Mock(return_value=0.09))

        self.assertEqual(RPGSystem(rng=rng).calculate_stress([]), 15)

    def test_same_seed_produces_same_rpg_results_and_personality(self):
        missions = [{"date": "1917-04-06", "claimsCount": 1, "enemyContacts": 3}]

        def results(seed):
            rpg = RPGSystem(seed=seed)
            return (
                rpg.calculate_fatigue(missions),
                rpg.calculate_morale(missions, "Active"),
                rpg.calculate_stress(missions),
                rpg.generate_personality(),
            )

        self.assertEqual(results(42), results(42))

    def test_personality_uses_injected_generator(self):
        rng = Mock()
        rng.randint.side_effect = [61, 29, 60, 26, 39, 83]
        rng.choice.return_value = "Disciplined"

        personality = RPGSystem(rng=rng).generate_personality()

        self.assertEqual(
            personality,
            {
                "aerial_skill": 61,
                "aggression": 29,
                "charisma": 60,
                "intelligence": 26,
                "physicality": 39,
                "professionalism": 83,
                "personality_trait": "Disciplined",
            },
        )

        rng.choice.assert_called_once_with(["Disciplined"])

    def test_different_seeds_produce_different_personalities(self):
        first = RPGSystem(seed=1).generate_personality()
        second = RPGSystem(seed=2).generate_personality()

        self.assertNotEqual(first, second)

    def test_rng_and_seed_are_mutually_exclusive(self):
        with self.assertRaisesRegex(ValueError, "Use rng or seed, not both"):
            RPGSystem(rng=Mock(), seed=1)

    def test_default_uses_production_random_generator(self):
        self.assertIs(RPGSystem().rng, random)

if __name__ == "__main__":
    unittest.main()
