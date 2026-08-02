import unittest
import os
from unittest.mock import patch, mock_open


from ..parsers.dossier_parser import WoFFDossierParser

def _encode_dossier(plaintext_lines: list, filename: str) -> bytes:
    """
    Helper de Teste: Aplica a camada de ofuscação (XOR + Hex + Contador)
    para simular um ficheiro Pilot{N}Dossier.txt real.
    """
    pName = filename.replace(".txt", "")
    
    # Replicar a geração de chave do WoFFDossierParser
    plainkey = "78CrztPRVzYQpYu90MnyW"
    soucet = sum(ord(c) for c in pName)
    sum_val = soucet % 128
    
    pos = sum_val % 10
    if pos == 0: pos = 9
    length = sum_val % 12
    if length == 0: length = 4
    
    prekey = "".join(plainkey[ind - 1] for ind in range(pos, pos + length))
    postkey = "".join(plainkey[lengt - 1] for lengt in range(length, length + pos))
    sp = chr(sum_val)
    key = prekey + sp + plainkey + postkey

    raw_data = bytearray()
    current_key = key
    
    for line in plaintext_lines:
        key_index = 0
        counter = 0x80  # Contador começa em 128 (0x80)
        
        for char in line:
            val = ord(char)
            k_char = ord(current_key[key_index])
            xor_val = val ^ k_char
            
            # Converter para Hex (maiúsculas, 2 dígitos)
            hex_str = f"{xor_val:02X}"
            raw_data.extend(hex_str.encode('ascii'))
            
            # Inserir byte contador
            raw_data.append(counter)
            
            # Manter contador entre 128 e 255 para o parser reconhecer como separador
            counter = 0x80 + ((counter - 0x80 + 1) % 128)
            
            key_index = (key_index + 1) % len(current_key)
            
        raw_data.extend(b"\r\n")
        current_key = current_key[::-1] # Inverter chave a cada linha
        
    return bytes(raw_data)


class TestWoFFDossierParser(unittest.TestCase):
    
    def setUp(self):
        self.parser = WoFFDossierParser()
        self.filename = "Pilot1Dossier.txt"
        
        # FIX: Usar "Null" em vez de "." para não confundir o parser de medalhas
        self.mock_lines = ["Null"] * 105 
        
        # Preencher os índices que o parser procura
        self.mock_lines[1] = "France"
        self.mock_lines[3] = "Capitaine"
        self.mock_lines[4] = "James"
        self.mock_lines[5] = "Hartley"
        self.mock_lines[11] = "1520"  # flminutes
        self.mock_lines[16] = "5"     # claims
        self.mock_lines[17] = "3"     # kills
        self.mock_lines[19] = "Medaille Militaire;1915-05-10"
        self.mock_lines[41] = "75"    # skill
        self.mock_lines[46] = "10"    # missions
        self.mock_lines[52] = "800"   # reputation
        self.mock_lines[83] = "Escadrille N 15"
        self.mock_lines[84] = "Nieuport_10C1"
        self.mock_lines[88] = "Savy"
        self.mock_lines[89] = "Flanders"
        self.mock_lines[92] = "Lyon"
        self.mock_lines[100] = "1"    # photo_id
        
        # Wingman na linha 104
        self.mock_lines[104] = "Lieutenant;John;Smith;3;5;In Service;0;0;0;0;0;6;1550;1500;9;2;8;8;1896;Reliable pilot.;75;21;651;1;19/7/1913;Chambery, Savoie, France;2;0;Medaille Militaire;Null;Null;Null;Null;Null;Null"

        self.encoded_data = _encode_dossier(self.mock_lines, self.filename)

    def test_parse_valid_dossier(self):
        """Testa decodificação de dossier com dados conhecidos."""
        with patch("builtins.open", mock_open(read_data=self.encoded_data)):
            ok = self.parser.parse(self.filename)
            
        self.assertTrue(ok)
        self.assertIsNotNone(self.parser.pilot)
        
        # Type narrowing para o Pyright compreender que não é None
        assert self.parser.pilot is not None
        
        self.assertEqual(self.parser.pilot.name, "James Hartley")
        self.assertEqual(self.parser.pilot.nation, "French")
        self.assertEqual(self.parser.pilot.photo, "1")
        self.assertEqual(self.parser.pilot.killsCount, 3)

    def test_parse_dossier_wrong_filename(self):
        """Testa que chave XOR errada não produz o piloto correto."""
        # Tentar ler com um nome de ficheiro diferente gera uma chave XOR diferente
        with patch("builtins.open", mock_open(read_data=self.encoded_data)):
            ok = self.parser.parse("WrongName.txt")
            
        # FIX: Com chave errada, ou falha completamente ou devolve dados corrompidos
        if ok and self.parser.pilot:
            # Type narrowing
            assert self.parser.pilot is not None
            self.assertNotEqual(self.parser.pilot.name, "James Hartley")
        else:
            self.assertFalse(ok) 

    def test_wingmen_extraction(self):
        """Testa extração de wingmen com patentes conhecidas."""
        with patch("builtins.open", mock_open(read_data=self.encoded_data)):
            self.parser.parse(self.filename)
            
        self.assertEqual(len(self.parser.wingmen), 1)
        w = self.parser.wingmen[0]
        self.assertEqual(w.rank, "Lieutenant")
        self.assertEqual(w.fName, "John")
        self.assertEqual(w.sName, "Smith")
        self.assertEqual(w.status, "In Service")
        self.assertIn("Reliable pilot", w.bio)

    def test_decorations_extraction(self):
        """Testa extração de medalhas nos índices 19-26."""
        with patch("builtins.open", mock_open(read_data=self.encoded_data)):
            self.parser.parse(self.filename)
            
        self.assertEqual(len(self.parser.decorations), 1)
        d = self.parser.decorations[0]
        self.assertEqual(d.name, "Medaille Militaire")
        self.assertEqual(d.date, "1915-05-10")

if __name__ == "__main__":
    unittest.main()
