"""LLM-Adapter-Layer (architecture.md §4 `app/adapters/llm/`).

Beherbergt sowohl das Grounding-Gate (`grounding.py`, C-008, ADR-003) als
auch — in späteren Stories — den eigentlichen LLM-API-Aufruf. Der
Grounding-Gate sitzt architektonisch VOR dem LLM-Adapter-Aufruf: kein Modul
des Order-Pfads darf dieses Paket importieren (BR-001, architecture.md §9).
"""

from __future__ import annotations
