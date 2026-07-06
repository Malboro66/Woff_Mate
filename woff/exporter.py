#!/usr/bin/env python3
"""
Exportador JSON (exporter.py)
══════════════════════════════════════════════════════════════════
Responsável por manter e escrever o ficheiro JSON consumido pela 
aplicação WoFFBase.

Funcionalidades:
- Thread-Safe: Usa um Lock reentrante para evitar condições de corrida.
- Escrita Atómica: Escreve num ficheiro temporário e substitui o original
  para evitar corrupção de dados em caso de falha.
- Deduplicação Inteligente: Faz merge de dados novos com registos 
  existentes usando chaves compostas (piloto + data + tipo, etc).
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List

# Importar os modelos de dados do módulo local
from models import WoFFPilot, WoFFMission, WoFFVictory, WoFFDecoration, WoFFExport

log = logging.getLogger("WoFFWatch")


class JSONExporter:
    def __init__(self, export_path: str, backup: bool = True, schema_version: str = "1.4"):
        self.export_path = Path(export_path)
        self.backup = backup
        self.schema_version = schema_version
        self._lock = threading.RLock()  # Lock reentrante para segurança em multi-threading
        self.export_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> WoFFExport:
        """Carrega o JSON existente ou cria uma estrutura vazia."""
        if not self.export_path.exists():
            return WoFFExport(meta={"created": datetime.now().isoformat()})
        try:
            with open(self.export_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            return WoFFExport(
                pilots      = d.get("pilots", []),
                missions    = d.get("missions", []),
                victories   = d.get("victories", []),
                decorations = d.get("decorations", []),
                diary       = d.get("diary", []),
                meta        = d.get("meta", {})
            )
        except Exception as e:
            log.error(f"Falha ao carregar export existente: {e}")
            return WoFFExport()

    def _atomic_write(self, data: dict) -> None:
        """Escrita atómica para evitar corrupção de ficheiros JSON."""
        tmp_path = self.export_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # Criar backup do ficheiro antigo antes de o substituir
        if self.backup and self.export_path.exists():
            bak_path = self.export_path.with_suffix(".json.bak")
            try:
                shutil.copy2(self.export_path, bak_path)
            except Exception as e:
                log.warning(f"Falha ao criar backup: {e}")
                
        # Substituição atómica (no mesmo sistema de ficheiros)
        os.replace(tmp_path, self.export_path)

    def merge_and_write(self,
                        pilot:       Optional[WoFFPilot],
                        missions:    List[WoFFMission],
                        victories:   List[WoFFVictory],
                        decorations: List[WoFFDecoration]) -> bool:
        """
        Faz merge dos novos dados extraídos com o histórico existente e 
        escreve no disco de forma segura.
        """
        with self._lock:
            exp = self.load()

            pilot_id = ""
            
            # ── Processar Piloto ──
            if pilot:
                existing = next(
                    (p for p in exp.pilots
                     if p.get("name","").lower() == pilot.name.lower()),
                    None
                )
                if existing:
                    pilot_id = existing["id"]
                    pd = asdict(pilot)
                    pd["id"] = pilot_id
                    # Atualiza o piloto mantendo a ordem na lista
                    exp.pilots = [pd if p["id"] == pilot_id else p for p in exp.pilots]
                    log.info(f"  Piloto actualizado: {pilot.name}")
                else:
                    pilot_id = pilot.id
                    exp.pilots.append(asdict(pilot))
                    log.info(f"  Novo piloto adicionado: {pilot.name}")
            else:
                # Se for TXT sem piloto definido, não adivinhamos o primeiro da lista
                # Apenas processamos se vier um pilot_id externamente definido
                pilot_id = next((m.pilotId for m in missions if m.pilotId), "")
                if not pilot_id:
                    log.warning("  Ficheiro de debrief sem piloto associado. Missões não associadas.")
                    return False

            # ── Processar Missões ──
            # Chave de deduplicação: piloto + data + tipo de missão + aeronave
            m_keys = {(m.get("pilotId",""), m.get("date",""), m.get("missionType",""), m.get("aircraft",""))
                      for m in exp.missions}
            added_m = 0
            for m in missions:
                m.pilotId = pilot_id
                k = (m.pilotId, m.date, m.missionType, m.aircraft)
                if k not in m_keys:
                    exp.missions.append(asdict(m))
                    m_keys.add(k)
                    added_m += 1

            # ── Processar Vitórias ──
            # Chave de deduplicação: piloto + data + hora + tipo de inimigo
            v_keys = {(v.get("pilotId",""), v.get("date",""), v.get("time",""), v.get("enemyType",""))
                      for v in exp.victories}
            added_v = 0
            for v in victories:
                v.pilotId = pilot_id
                k = (v.pilotId, v.date, v.time, v.enemyType)
                if k not in v_keys:
                    exp.victories.append(asdict(v))
                    v_keys.add(k)
                    added_v += 1

            # ── Processar Condecorações ──
            # Chave de deduplicação: piloto + nome da condecoração
            d_keys = {(d.get("pilotId",""), d.get("name","")) for d in exp.decorations}
            added_d = 0
            for d in decorations:
                d.pilotId = pilot_id
                k = (d.pilotId, d.name)
                if k not in d_keys:
                    exp.decorations.append(asdict(d))
                    d_keys.add(k)
                    added_d += 1

            if added_m or added_v or added_d:
                log.info(f"  + {added_m} missões, {added_v} vitórias, {added_d} condecorações")

            # ── Atualizar Metadados e Escrever ──
            exp.meta["last_updated"] = datetime.now().isoformat()
            exp.meta["source"]       = f"WoFF BHaH II Watchdog v{self.schema_version}"
            exp.meta["schema_version"] = self.schema_version

            try:
                self._atomic_write(asdict(exp))
                size_kb = self.export_path.stat().st_size / 1024
                log.info(f"  ✓ Export escrito: {self.export_path} ({size_kb:.1f} KB)")
                return True
            except Exception as e:
                log.error(f"Falha ao escrever export: {e}")
                return False