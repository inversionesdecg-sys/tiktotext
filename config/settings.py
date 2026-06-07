"""
Configuración del usuario. Todo se lee desde ~/.tiktotex/
Nunca hay credenciales hardcodeadas.
"""
import json
import os
from pathlib import Path

# ── Directorio de usuario ─────────────────────────────────────────────────────
USER_DIR = Path.home() / ".tiktotex"
CONFIG_FILE   = USER_DIR / "config.json"
TIKTOK_COOKIES = USER_DIR / "tiktok_cookies.txt"
YOUTUBE_COOKIES = USER_DIR / "youtube_cookies.txt"


def load_user_config() -> dict:
    """Carga ~/.tiktotex/config.json. Devuelve {} si no existe."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_user_config(data: dict) -> None:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_user_config()
    existing.update(data)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)


def is_setup_complete() -> bool:
    cfg = load_user_config()
    return bool(cfg.get("tiktok_user")) and TIKTOK_COOKIES.exists()


# ── Valores de sesión (cargados en runtime) ───────────────────────────────────
def get_tiktok_user() -> str:
    user = load_user_config().get("tiktok_user", "")
    if not user:
        raise RuntimeError("Setup incompleto. Ejecutá: python tiktotex.py --setup")
    return user


def get_browser_path() -> str:
    """Devuelve el path al browser configurado, o busca Brave/Chrome automáticamente."""
    cfg = load_user_config()
    if cfg.get("browser_path") and os.path.exists(cfg["browser_path"]):
        return cfg["browser_path"]
    candidates = [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise RuntimeError(
        "No se encontró un browser compatible. "
        "Configurá el path con: python tiktotex.py --setup"
    )


# ── Settings con override por variable de entorno ─────────────────────────────
cfg = load_user_config()

OUTPUT_DIR           = os.getenv("OUTPUT_DIR",   cfg.get("output_dir",   r"C:\Users\cesar\Desktop\tiktokfav"))
OLLAMA_MODEL         = os.getenv("OLLAMA_MODEL", cfg.get("ollama_model", "gpt-oss:120b-cloud"))
OLLAMA_URL           = os.getenv("OLLAMA_URL",   cfg.get("ollama_url",   "http://localhost:11434/api/generate"))
TIKTOK_LIKED_LIMIT   = int(os.getenv("TIKTOK_LIKED_LIMIT",   str(cfg.get("tiktok_liked_limit",   1000))))
TRANSCRIPT_MAX_CHARS = int(os.getenv("TRANSCRIPT_MAX_CHARS", str(cfg.get("transcript_max_chars", 7000))))

# Workers paralelos — cuántos videos se procesan simultáneamente
# Whisper en CPU: 2-3 es razonable. Con GPU podés subir a 5+.
PARALLEL_WORKERS = int(os.getenv("PARALLEL_WORKERS", str(cfg.get("parallel_workers", 2))))

# Whisper local — modelo a usar (tiny/base/small/medium/large)
WHISPER_MODEL    = os.getenv("WHISPER_MODEL",    cfg.get("whisper_model",    "small"))
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", cfg.get("whisper_language", "es"))
