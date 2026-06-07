"""
Setup wizard de primera vez para Tiktotex.
Ejecutar con: python tiktotex.py --setup
"""
import os
import shutil
from pathlib import Path


def run_setup() -> None:
    from config.settings import USER_DIR, TIKTOK_COOKIES, YOUTUBE_COOKIES, save_user_config

    print("=" * 60)
    print("  Tiktotex — Configuración inicial")
    print("=" * 60)
    print(f"\nTus datos se guardarán en: {USER_DIR}\n")

    # ── Paso 1: usuario TikTok ─────────────────────────────────────────────
    print("PASO 1 — Usuario TikTok")
    print("─" * 40)
    tiktok_user = input("  Tu nombre de usuario (@...): ").strip().lstrip("@")
    if not tiktok_user:
        print("  ERROR: el usuario no puede estar vacío.")
        return

    # ── Paso 2: cookies TikTok ─────────────────────────────────────────────
    print("\nPASO 2 — Cookies de TikTok")
    print("─" * 40)
    print("  1. Instalá 'Get cookies.txt LOCALLY' en Chrome/Brave")
    print("  2. Entrá a https://www.tiktok.com con tu sesión iniciada")
    print("  3. Extensión → Export → guardá el archivo")
    cookies_path = input("  Ruta al archivo cookies.txt: ").strip().strip('"')

    if not os.path.isfile(cookies_path):
        msg = "es una carpeta" if os.path.isdir(cookies_path) else "no existe"
        print(f"  ERROR: {msg}. Ejemplo: C:\\Users\\cesar\\Downloads\\tiktok_cookies.txt")
        return

    USER_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cookies_path, TIKTOK_COOKIES)
    print(f"  Guardado en: {TIKTOK_COOKIES}")

    # ── Paso 3: cookies YouTube (opcional) ────────────────────────────────
    print("\nPASO 3 — Cookies de YouTube (opcional, Enter para omitir)")
    print("─" * 40)
    yt_path = input("  Ruta al cookies.txt de YouTube: ").strip().strip('"')
    if yt_path:
        if os.path.isfile(yt_path):
            shutil.copy2(yt_path, YOUTUBE_COOKIES)
            print(f"  Guardado en: {YOUTUBE_COOKIES}")
        else:
            print("  Archivo no encontrado, omitiendo YouTube.")

    # ── Paso 4: browser ────────────────────────────────────────────────────
    print("\nPASO 4 — Browser (para acceder a TikTok)")
    print("─" * 40)
    browser_path = _detect_or_ask_browser()

    # ── Paso 5: carpeta de salida ──────────────────────────────────────────
    print("\nPASO 5 — Carpeta de salida para los archivos .md")
    print("─" * 40)
    default_out = str(Path.home() / "Tiktotex_Digest")
    raw = input(f"  Ruta (Enter = {default_out}): ").strip().strip('"')
    output_dir = raw or default_out

    # ── Paso 6: modelo Ollama ──────────────────────────────────────────────
    print("\nPASO 6 — Modelo Ollama para resúmenes")
    print("─" * 40)
    print("  Opciones: deepseek-v3, llama3.1, mistral, phi3")
    raw = input("  Modelo (Enter = deepseek-v3): ").strip()
    ollama_model = raw or "deepseek-v3"

    # ── Paso 7: modelo Whisper ─────────────────────────────────────────────
    print("\nPASO 7 — Modelo Whisper para transcripciones locales")
    print("─" * 40)
    print("  tiny (rápido) | base | small (recomendado) | medium | large (lento)")
    raw = input("  Modelo (Enter = small): ").strip()
    whisper_model = raw or "small"

    # ── Guardar ────────────────────────────────────────────────────────────
    save_user_config({
        "tiktok_user":    tiktok_user,
        "browser_path":   browser_path,
        "output_dir":     output_dir,
        "ollama_model":   ollama_model,
        "whisper_model":  whisper_model,
    })

    print("\n" + "=" * 60)
    print("  Configuración guardada.")
    print(f"  Usuario:  @{tiktok_user}")
    print(f"  Salida:   {output_dir}")
    print(f"  Ollama:   {ollama_model}")
    print(f"  Whisper:  {whisper_model}")
    print("\n  Listo para usar: python tiktotex.py")
    print("=" * 60)


def _detect_or_ask_browser() -> str:
    candidates = [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe"),
    ]
    names = {"brave.exe": "Brave", "chrome.exe": "Chrome"}
    found = [p for p in candidates if os.path.exists(p)]

    if found:
        detected = found[0]
        label = names.get(Path(detected).name, detected)
        raw = input(f"  Se detectó {label}. Enter para usarlo (o pegá otra ruta): ").strip().strip('"')
        return raw if raw and os.path.exists(raw) else detected

    path = input("  No se detectó browser. Pegá la ruta al ejecutable: ").strip().strip('"')
    return path
