#!/usr/bin/env python3
"""
Testes Unitários para a Normalização (tests/test_normalization.py)
══════════════════════════════════════════════════════════════════
"""

import os

import unittest
import xml.etree.ElementTree as ET

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from normalization import (
    normalize_nation,
    normalize_mission_type,
    normalize_status,
    normalize_victory_type,
    normalize_date
)

class TestNormalization(unittest.TestCase):

    # ── Testes de Nação ──

    def test_normalize_nation_known(self):
        self.assertEqual(normalize_nation("RFC"), "RFC")
        self.assertEqual(normalize_nation("royal flying corps"), "RFC")
        self.assertEqual(normalize_nation("German"), "German")
        self.assertEqual(normalize_nation("USA"), "American")
        self.assertEqual(normalize_nation("france"), "French")

    def test_normalize_nation_unknown(self):
        """Testa se retorna o fallback ('RFC') para nações desconhecidas."""
        self.assertEqual(normalize_nation("Martian"), "RFC")
        self.assertEqual(normalize_nation(""), "RFC")

    # ── Testes de Tipo de Missão ──

    def test_normalize_mission_type_known(self):
        self.assertEqual(normalize_mission_type("Offensive Patrol"), "Offensive Patrol (OP)")
        self.assertEqual(normalize_mission_type("fighter op"), "Offensive Patrol (OP)")
        self.assertEqual(normalize_mission_type("Bombing"), "Bombing Raid (Tactical)")

    def test_normalize_mission_type_unknown(self):
        """Testa se retorna o texto original (limpo) para tipos desconhecidos."""
        self.assertEqual(normalize_mission_type("Reconnaissance"), "Reconnaissance")
        self.assertEqual(normalize_mission_type(""), "")

    # ── Testes de Status do Piloto ──

    def test_normalize_status_kia(self):
        self.assertEqual(normalize_status("Killed in Action"), "KIA")
        self.assertEqual(normalize_status("KIA"), "KIA")

    def test_normalize_status_pow_mia(self):
        self.assertEqual(normalize_status("Captured by enemy"), "PoW")
        self.assertEqual(normalize_status("Missing in action"), "MIA")

    def test_normalize_status_false_positive(self):
        """Garantia que a palavra 'deadline' não ativa o status 'dead'."""
        self.assertEqual(normalize_status("Missed a deadline"), "Active")

    def test_normalize_status_wounded_no_root(self):
        """Testa ferimentos quando não há nó XML para avaliar gravidade."""
        self.assertEqual(normalize_status("In Hospital"), "Lightly Wounded")
        self.assertEqual(normalize_status("lightly wounded"), "Lightly Wounded")

    def test_normalize_status_severe_wound_with_root(self):
        """Testa se a gravidade é lida corretamente do nó XML."""
        xml_str = "<Root><WoundSeverity>Serious</WoundSeverity></Root>"
        root = ET.fromstring(xml_str)
        self.assertEqual(normalize_status("In Hospital", root), "Seriously Wounded")

        xml_str = "<Root><WoundSeverity>Light</WoundSeverity></Root>"
        root = ET.fromstring(xml_str)
        self.assertEqual(normalize_status("wound", root), "Lightly Wounded")

    def test_normalize_status_active(self):
        self.assertEqual(normalize_status("Active"), "Active")
        self.assertEqual(normalize_status(""), "Active")

    # ── Testes de Tipo de Vitória ──

    def test_normalize_victory_type(self):
        self.assertEqual(normalize_victory_type("went down in flames"), "Destroyed — In Flames")
        self.assertEqual(normalize_victory_type("OOC"), "Out of Control (OOC)")
        self.assertEqual(normalize_victory_type("Driven down"), "Driven Down (Unconfirmed)")
        self.assertEqual(normalize_victory_type("Unknown event"), "Out of Control (OOC)") # Fallback

    # ── Testes de Normalização de Datas ──

    def test_normalize_date_iso(self):
        self.assertEqual(normalize_date("1917-04-06"), "1917-04-06")

    def test_normalize_date_dd_mm_yyyy(self):
        self.assertEqual(normalize_date("06/04/1917"), "1917-04-06")
        self.assertEqual(normalize_date("6.4.1917"), "1917-04-06")

    def test_normalize_date_yyyy_mm_dd(self):
        self.assertEqual(normalize_date("1917/04/06"), "1917-04-06")

    def test_normalize_date_text_english(self):
        self.assertEqual(normalize_date("6 April 1917"), "1917-04-06")
        self.assertEqual(normalize_date("April 15, 1917"), "1917-04-15")
        self.assertEqual(normalize_date("Sep 1 1918"), "1918-09-01")

    def test_normalize_date_text_french(self):
        self.assertEqual(normalize_date("6 Avril 1917"), "1917-04-06")
        self.assertEqual(normalize_date("15 mai 1918"), "1918-05-15")

    def test_normalize_date_empty(self):
        self.assertEqual(normalize_date(""), "")

    def test_normalize_date_invalid(self):
        self.assertEqual(normalize_date("Tomorrow"), "Tomorrow")

if __name__ == "__main__":
    unittest.main()