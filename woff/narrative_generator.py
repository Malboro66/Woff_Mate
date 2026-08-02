#!/usr/bin/env python3
"""
Gerador de Narrativas (narrative_generator.py)
══════════════════════════════════════════════════════════════════
Gera entradas de Diário de Bordo altamente contextuais, baseadas
nos dados exatos extraídos da missão, eventos de vida e wingmen.
══════════════════════════════════════════════════════════════════
"""
import logging
from typing import Optional, Dict, Any

log = logging.getLogger("WoFFWatch")

class NarrativeGenerator:
    def __init__(self):
        pass

    def generate(self, pilot_name: str, mission_data: Dict[str, Any]) -> str:
        """
        Gera uma narrativa baseada nos dados da missão.
        mission_data: dicionário com chaves como date, missionType, aircraft, etc.
        """
        date = mission_data.get("date", "Data desconhecida")
        mission_type = mission_data.get("missionType", "patrulha")
        aircraft = str(mission_data.get("aircraft", "aeronave desconhecida").replace("_", " "))
        weather = str(mission_data.get("weather", "")).lower()
        claims = mission_data.get("claimsCount", 0)
        enemy_type = mission_data.get("enemyType", "")
        result = str(mission_data.get("result", "")).lower()
        wounds = int(mission_data.get("woundsReceived", 0))
        damage = int(mission_data.get("damageReceived", 0))

        # 1. Introdução (Data e Clima)
        weather_text = "O tempo estava instável, com nuvens pesadas." if "cloud" in weather or "overcast" in weather else \
                       "O céu estava limpo, uma raridade nestes dias de outono." if "clear" in weather else \
                       "A visibilidade era reduzida devido à neblina e chuva." if "rain" in weather or "fog" in weather else \
                       "As condições meteorológicas eram típicas para a época."
        
        narrative = f"{date}\nHoje voámos numa {mission_type} no meu {aircraft}. {weather_text}\n\n"

        # 2. Ação (Contactos e Vitórias)
        contacts = mission_data.get("enemyContacts", 0)
        if contacts not in (0, "0", ""):
            narrative += f"Encontrámos {contacts} aeronaves inimigas. "
            if claims not in (0, "0", ""):
                enemy_text = f"um {enemy_type}" if enemy_type else "uma aeronave inimiga"
                if claims in (1, "1"):
                    narrative += f"Consegui encurralar {enemy_text} e abatê-lo. Foi uma vitória suada, mas necessária para manter a moral da esquadrilha alta.\n"
                else:
                    narrative += f"Hoje tive um dia de sorte, abati {claims} aeronaves inimigas. O céu pertenceu-nos hoje.\n"
            else:
                narrative += "Apesar dos combates aéreos, não consegui confirmar nenhum abate. Eles são escorregadios como enguias.\n"
        else:
            narrative += "A patrulha decorreu sem incidentes. O espaço aéreo estava pacífico, embora a artilharia terrestre nunca pare de trovejar lá em baixo.\n"

        # 3. Conclusão (Danos e Resultado)
        if wounds > 0:
            narrative += "\nO meu avião foi atingido e eu fui ferido. Sinto uma dor lancinante, mas os médicos dizem que vou sobreviver. Preciso de descanso."
        elif "force" in result:
            narrative += "\nO motor começou a falhar e tive de fazer uma aterragem forçada. Foi um milagre ter saído ileso da máquina destroçada."
        elif damage > 0:
            narrative += "\nRegressei à base com o avião crivado de balas. A oficina vai ter trabalho nos próximos dias, mas estou vivo para contar a história."
        else:
            narrative += "\nAterrei em segurança na base. Mais um dia nesta guerra que parece não ter fim."

        return narrative

    def generate_life_event(self, new_status: str, old_status: Optional[str], new_rank: str, old_rank: Optional[str]) -> Optional[str]:
        """Gera texto para eventos de vida (ferimentos, promoções, etc.)"""
        event_text = ""
        
        # Se o piloto é novo (old_status é None)
        if old_status is None:
            return f"Cheguei à esquadrilha como {new_rank}. Sinto uma mistura de ansiedade e patriotismo. É o início da minha jornada nestes céus."
        
        # Mudança de Status (Ferimentos / Hospital / Licença)
        if old_status != new_status:
            new_s = new_status.lower()
            old_s = old_status.lower()
            
            if "wound" in new_s or "hospital" in new_s:
                event_text += "Acordei com dores lancinantes. O médico disse que fui atingido e vou precisar de semanas para recuperar. Fico preso nesta cama de hospital enquanto os meus camaradas continuam a lutar no céu.\n"
            elif "leave" in new_s:
                event_text += "Recebi autorização para ir de licença. Vou aproveitar este tempo longe da frente para limpar a mente destes meses de combate interminável.\n"
            elif "in service" in new_s or "active" in new_s:
                if "wound" in old_s or "hospital" in old_s:
                    event_text += "Finalmente recebi alta médica! É bom estar de volta à esquadrilha. O cheiro a óleo e lona nunca cheirou tão bem. Estou pronto para voltar a voar.\n"
                elif "leave" in old_s:
                    event_text += "Regressei da licença. A paz e o sossego acabaram, mas é bom estar de volta com os rapazes.\n"
                    
        # Promoção
        if old_rank != new_rank and new_rank:
            if event_text:
                event_text += "\n"
            event_text += f"Fui promovido a {new_rank}! É uma honra, mas também traz um peso extra nos ombros. Os camaradas festejaram no mess esta noite."
            
        return event_text if event_text else None

    def generate_wingman_event(self, wingman_name: str, event_type: str) -> Optional[str]:
        """Gera texto para eventos de vida de wingmen (mortes, ferimentos, chegadas)."""
        if event_type == "wounded":
            return f"O meu camarada {wingman_name} foi ferido em combate e evacuado para o hospital. O esquadrão sente a sua falta."
        elif event_type == "kia":
            return f"Recebi a notícia de que {wingman_name} foi abatido sobre as linhas inimigas. Era um bom piloto e sentir-lhe-ei a falta no mess esta noite."
        elif event_type == "missing":
            return f"Perdi o contacto com {wingman_name} durante a confusão no ar. Temendo o pior para o seu destino."
        elif event_type == "new":
            return f"Recebemos um novo elemento na esquadrilha: {wingman_name}. Espero que esteja à altura do que o céu de Flandres nos reserva."
        return None

# Instância global
narrative_generator = NarrativeGenerator()