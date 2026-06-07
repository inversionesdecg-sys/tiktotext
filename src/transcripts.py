"""
Extracción de transcripciones:
  - TikTok: yt-dlp obtiene descripción + descarga audio -> Whisper transcribe
  - YouTube: yt-dlp subtítulos VTT nativos -> fallback Whisper

Todas las funciones públicas devuelven (transcript: str, description: str).
"""
import glob
import json
import os
import subprocess
import tempfile

from config.settings import WHISPER_MODEL, WHISPER_LANGUAGE


def _ffmpeg_exe() -> str:
    """Devuelve el path al ffmpeg bundled con imageio (sin necesitar instalación global)."""
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


# ── TikTok via Whisper local ──────────────────────────────────────────────────

def get_tiktok_transcript(url: str) -> tuple[str, str]:
    """Devuelve (transcripción, descripción_del_video)."""
    description = _get_video_description(url)
    print(f"  Descargando audio: {url}")
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = _download_audio(url, tmpdir)
        if not audio_path:
            print("  No se pudo descargar el audio.")
            return "", description
        text = _whisper(audio_path)
    if text:
        print(f"  Transcripción obtenida ({len(text)} chars).")
    else:
        print("  Sin transcripción disponible.")
    return text, description


# ── YouTube via yt-dlp subtítulos ─────────────────────────────────────────────

def get_youtube_transcript(url: str) -> tuple[str, str]:
    """Devuelve (transcripción, descripción_del_video)."""
    description = _get_video_description(url)
    print(f"  Descargando subtítulos YouTube: {url}")
    video_id = url.split("v=")[-1].split("&")[0] if "v=" in url else url.split("/")[-1]
    subprocess.run(
        ["yt-dlp",
         "--write-subs", "--write-auto-subs",
         "--sub-langs", "es,en",
         "--skip-download", "--convert-subs", "vtt",
         "--ffmpeg-location", _ffmpeg_exe(),
         "-o", video_id, url],
        capture_output=True,
    )
    text = _read_and_cleanup_vtt(prefix=video_id)
    if text:
        print(f"  Transcripción obtenida ({len(text)} chars).")
        return text, description

    # Fallback: descargar audio y usar Whisper
    print("  Sin subtítulos, usando Whisper...")
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = _download_audio(url, tmpdir)
        if not audio_path:
            print("  No se pudo descargar el audio.")
            return "", description
        text = _whisper(audio_path)
    if text:
        print(f"  Transcripción obtenida ({len(text)} chars).")
    else:
        print("  Sin transcripción disponible.")
    return text, description


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_video_description(url: str) -> str:
    """Obtiene la descripción del video via yt-dlp --dump-json."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-download", "--no-warnings", url],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode == 0 and result.stdout.strip():
            info = json.loads(result.stdout.strip())
            return info.get("description", "") or info.get("title", "")
    except Exception:
        pass
    return ""


def _download_audio(url: str, tmpdir: str) -> str:
    """Descarga el audio del video en tmpdir. Devuelve el path del archivo."""
    out_template = os.path.join(tmpdir, "audio.%(ext)s")
    subprocess.run(
        ["yt-dlp", "-x", "--audio-format", "mp3",
         "--ffmpeg-location", _ffmpeg_exe(),
         "-o", out_template, url],
        capture_output=True,
    )
    for f in os.listdir(tmpdir):
        if f.startswith("audio"):
            return os.path.join(tmpdir, f)
    return ""


def _whisper(audio_path: str) -> str:
    """Transcribe con faster-whisper (preferido) o openai-whisper."""
    print(f"  Transcribiendo con Whisper ({WHISPER_MODEL})...")
    ffmpeg = _ffmpeg_exe()
    env = os.environ.copy()
    env["PATH"] = os.path.dirname(ffmpeg) + os.pathsep + env.get("PATH", "")

    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(audio_path, language=WHISPER_LANGUAGE)
        return " ".join(s.text.strip() for s in segments)
    except ImportError:
        pass

    try:
        import whisper
        model = whisper.load_model(WHISPER_MODEL)
        result = model.transcribe(audio_path, language=WHISPER_LANGUAGE)
        return result.get("text", "").strip()
    except ImportError:
        print("  ERROR: instala faster-whisper o openai-whisper.")
        return ""


def _read_and_cleanup_vtt(prefix: str = "") -> str:
    pattern = f"{prefix}*.vtt" if prefix else "*.vtt"
    files = glob.glob(pattern)
    if not files:
        return ""
    text = _parse_vtt(files[0])
    for f in files:
        try:
            os.remove(f)
        except OSError:
            pass
    return text


def _parse_vtt(filepath: str) -> str:
    lines = []
    seen: set[str] = set()
    with open(filepath, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("WEBVTT") or "-->" in line:
                continue
            if line.startswith(("NOTE", "align:")):
                continue
            if line not in seen:
                lines.append(line)
                seen.add(line)
    return " ".join(lines)
