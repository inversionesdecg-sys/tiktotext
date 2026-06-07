"""
Registro persistente de videos ya procesados.
Archivo: Digest/.processed.json  →  { url: {processed_at, filename, source} }

El estado se carga una sola vez en memoria y se descarga al disco en cada
marca (mark_processed), para no releer el archivo en cada consulta del loop.
"""
import json
import os
from datetime import datetime
from config.settings import OUTPUT_DIR

_STATE_FILE = os.path.join(OUTPUT_DIR, ".processed.json")
_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        if os.path.exists(_STATE_FILE):
            with open(_STATE_FILE, encoding="utf-8") as f:
                _cache = json.load(f)
        else:
            _cache = {}
    return _cache


def _save(state: dict) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def is_processed(url: str) -> bool:
    return url in _load()


def mark_processed(url: str, filename: str, source: str) -> None:
    state = _load()
    state[url] = {
        "processed_at": datetime.now().isoformat(),
        "filename": filename,
        "source": source,
    }
    _save(state)


def get_stats() -> dict:
    state = _load()
    by_source: dict[str, int] = {}
    for entry in state.values():
        s = entry.get("source", "unknown")
        by_source[s] = by_source.get(s, 0) + 1
    return {"total": len(state), "by_source": by_source}
