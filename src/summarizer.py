import subprocess
import time

import requests

from config.settings import OLLAMA_MODEL, OLLAMA_URL, TRANSCRIPT_MAX_CHARS

_PROMPT = """\
Resume el siguiente texto en Markdown con estas secciones exactas:

## Título sugerido
## Puntos clave
## Sentimiento general
## Resumen

Texto:
{text}"""


def _ensure_ollama() -> None:
    """Verifica que Ollama esté corriendo; si no, lo lanza en segundo plano."""
    try:
        requests.get("http://localhost:11434", timeout=3)
        return  # ya está corriendo
    except Exception:
        pass

    print("  Ollama no está corriendo, iniciando...")
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    # Esperar hasta que responda (máx 15s)
    for _ in range(15):
        time.sleep(1)
        try:
            requests.get("http://localhost:11434", timeout=2)
            print("  Ollama listo.")
            return
        except Exception:
            pass
    print("  ADVERTENCIA: Ollama no respondió a tiempo.")


def summarize(text: str) -> str:
    _ensure_ollama()
    print(f"  Resumiendo con {OLLAMA_MODEL} ({min(len(text), TRANSCRIPT_MAX_CHARS)} chars)...")
    payload = {
        "model":  OLLAMA_MODEL,
        "prompt": _PROMPT.format(text=text[:TRANSCRIPT_MAX_CHARS]),
        "stream": False,
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=300)
    resp.raise_for_status()
    result = resp.json().get("response", "").strip()
    print(f"  Resumen generado ({len(result)} chars).")
    return result
