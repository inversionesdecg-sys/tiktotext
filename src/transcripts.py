"""
Extracción de transcripciones:
  - TikTok video:    audio → Whisper; si solo música → frames del video → OCR
  - TikTok carousel: imágenes directas → OCR  (URL /photo/)
  - YouTube:         subtítulos VTT nativos → fallback Whisper

Todas las funciones públicas devuelven (transcript: str, description: str).
"""
import asyncio
import glob
import json
import os
import shutil
import subprocess
import tempfile

from config.settings import WHISPER_MODEL, WHISPER_LANGUAGE

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}


# ── ffmpeg helper ─────────────────────────────────────────────────────────────

def _ffmpeg_exe() -> str:
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


# ── TikTok ────────────────────────────────────────────────────────────────────

def get_tiktok_transcript(url: str) -> tuple[str, str]:
    """Devuelve (transcripción, descripción_del_video).

    - Carruseles (/photo/): descarga imágenes → OCR directo.
    - Videos: Whisper; si audio = solo música → extrae frames → OCR.
    - Si hay voz Y texto visual, combina ambos.
    """
    description = _get_video_description(url)

    if "/photo/" in url:
        # ── Carrusel de imágenes ─────────────────────────────────────────────
        print(f"  Carrusel detectado — descargando imágenes: {url}")
        text = _get_carousel_ocr(url)
        if not text:
            print("  Sin texto extraíble en el carrusel.")
        else:
            print(f"  [OCR carrusel OK] {len(text)} chars.")
        return text, description

    # ── Video normal ──────────────────────────────────────────────────────────
    print(f"  Descargando audio: {url}")
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = _download_audio(url, tmpdir)
        audio_text = _whisper(audio_path) if audio_path else ""

    if audio_text:
        print(f"  [Whisper OK] {len(audio_text)} chars.")
    else:
        print("  Sin transcripción de audio.")

    frames_text = ""
    if _is_music_only(audio_text):
        print("  Audio sin voz — extrayendo texto de frames...")
        frames_text = _get_video_frames_ocr(url)
        if frames_text:
            print(f"  [OCR frames OK] {len(frames_text)} chars.")
        else:
            print("  Sin texto visible en frames.")

    return _combine(audio_text, frames_text), description


# ── YouTube ───────────────────────────────────────────────────────────────────

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


# ── OCR: carrusel ─────────────────────────────────────────────────────────────

def _get_carousel_ocr(url: str) -> str:
    """Descarga imágenes del carrusel TikTok y hace OCR."""
    tmpdir = tempfile.mkdtemp(prefix="tiktok_carousel_")
    try:
        images = _download_carousel_images(url, tmpdir)
        if images:
            print(f"  {len(images)} imágenes descargadas del carrusel.")
            return _ocr_frames(images)

        # Fallback: yt-dlp convierte el carrusel en video slideshow
        print("  Descarga directa fallida — usando slideshow de video...")
        video_path = _download_video(url, tmpdir)
        if not video_path:
            return ""
        # Muestreo denso: cada 2 segundos cubre cada slide del carrusel
        frames = _extract_frames(video_path, tmpdir, interval_sec=2, max_frames=30)
        return _ocr_frames(frames) if frames else ""
    except Exception as e:
        print(f"  [OCR carrusel] Error: {e}")
        return ""
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _download_carousel_images(url: str, tmpdir: str) -> list:
    """Descarga imágenes del carrusel TikTok vía Playwright.

    TikTok /photo/ URLs no son soportadas por yt-dlp.
    Usamos Playwright headless para cargar la página y obtener las URLs
    de imagen del DOM (tiktokcdn.com), luego las descargamos.
    """
    import asyncio
    return asyncio.run(_playwright_carousel(url, tmpdir))


async def _playwright_carousel(url: str, tmpdir: str) -> list:
    """Abre la URL del carrusel con Brave + cookies TikTok del usuario.

    Usa CDP para capturar los bytes de cada imagen mientras el browser
    las descarga — mismo patrón que url_fetchers para colecciones.
    """
    import base64
    try:
        from playwright.async_api import async_playwright
        from config.settings import TIKTOK_COOKIES, get_browser_path
    except ImportError as e:
        print(f"  [OCR carrusel] Import error: {e}")
        return []

    # Cargar cookies TikTok del usuario
    cookies: list = []
    try:
        with open(TIKTOK_COOKIES, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 7:
                    continue
                domain, _flag, path, _secure, _expiry, name, value = parts[:7]
                if "tiktok.com" in domain and name and value:
                    cookies.append({"name": name, "value": value,
                                    "domain": ".tiktok.com", "path": "/"})
    except Exception as e:
        print(f"  [OCR carrusel] No se pudieron cargar cookies: {e}")

    try:
        browser_path = get_browser_path()
    except Exception:
        browser_path = None

    try:
        async with async_playwright() as p:
            launch_kwargs = {"headless": True}
            if browser_path:
                launch_kwargs["executable_path"] = browser_path

            browser = await p.chromium.launch(**launch_kwargs)
            ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
            if cookies:
                await ctx.add_cookies(cookies)

            page = await ctx.new_page()

            # CDP: interceptar bytes de imágenes del carrusel mientras se descargan
            cdp = await ctx.new_cdp_session(page)
            await cdp.send("Network.enable")

            # Mapear requestId → URL para imágenes del carrusel
            carousel_requests: dict = {}

            def _on_request(event: dict) -> None:
                req = event.get("request", {})
                req_url = req.get("url", "")
                if "tiktokcdn.com" in req_url and "photomode" in req_url:
                    rid = event.get("requestId")
                    if rid:
                        carousel_requests[rid] = req_url

            cdp.on("Network.requestWillBeSent", _on_request)

            try:
                await page.goto(url, timeout=20000, wait_until="domcontentloaded")
            except Exception:
                pass
            await asyncio.sleep(6)

            await browser.close()

        if not carousel_requests:
            print("  [OCR carrusel] Sin imágenes capturadas via CDP.")
            return []

        print(f"  {len(carousel_requests)} imágenes del carrusel capturadas.")

        # Descargar imágenes con requests usando referer TikTok
        saved: list = []
        req_headers = {
            "Referer": "https://www.tiktok.com/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        import urllib.request
        for i, (rid, img_url) in enumerate(carousel_requests.items()):
            dest = os.path.join(tmpdir, f"img_{i:03d}.jpg")
            try:
                req = urllib.request.Request(img_url, headers=req_headers)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    with open(dest, "wb") as f:
                        f.write(resp.read())
                if os.path.exists(dest) and os.path.getsize(dest) > 1000:
                    saved.append(dest)
            except Exception as e:
                print(f"  img_{i} error: {e}")

        return saved

    except Exception as e:
        print(f"  [OCR carrusel Playwright] Error: {e}")
        import traceback
        traceback.print_exc()
        return []


# ── OCR: frames de video ──────────────────────────────────────────────────────

def _is_music_only(text: str) -> bool:
    """True cuando el audio no tiene voz real (vacío o muy corto)."""
    return not text or len(text.strip()) < 50


def _get_video_frames_ocr(url: str) -> str:
    """Descarga video, extrae frames espaciados, hace OCR."""
    tmpdir = tempfile.mkdtemp(prefix="tiktok_ocr_")
    try:
        video_path = _download_video(url, tmpdir)
        if not video_path:
            return ""
        frames = _extract_frames(video_path, tmpdir)
        return _ocr_frames(frames) if frames else ""
    except Exception as e:
        print(f"  [OCR video] Error: {e}")
        return ""
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _download_video(url: str, tmpdir: str) -> str:
    """Descarga video en resolución baja para extracción de frames."""
    ffmpeg = _ffmpeg_exe()
    video_path = os.path.join(tmpdir, "video.mp4")
    result = subprocess.run(
        ["yt-dlp", "--ffmpeg-location", ffmpeg,
         "-f", "best[height<=480]/best",
         "-o", video_path, "--no-playlist", "--no-warnings", url],
        capture_output=True, timeout=120,
    )
    return video_path if result.returncode == 0 and os.path.exists(video_path) else ""


def _extract_frames(video_path: str, tmpdir: str,
                    interval_sec: int = 0, max_frames: int = 10) -> list:
    """Extrae frames de un video.

    interval_sec=0 → timestamps fijos optimizados para videos de 15-60s.
    interval_sec>0 → muestreo denso cada N segundos (para carruseles como slideshow).
    """
    ffmpeg = _ffmpeg_exe()

    if interval_sec > 0:
        timestamps = list(range(1, interval_sec * max_frames, interval_sec))[:max_frames]
    else:
        timestamps = [1, 4, 8, 12, 16, 20, 25, 30, 40, 50]

    frames = []
    for i, t in enumerate(timestamps):
        out = os.path.join(tmpdir, f"frame_{i:03d}.jpg")
        subprocess.run(
            [ffmpeg, "-ss", str(t), "-i", video_path,
             "-frames:v", "1", "-q:v", "2", out, "-loglevel", "error"],
            capture_output=True, timeout=10,
        )
        if os.path.exists(out):
            frames.append(out)
    return frames


def _ocr_frames(frame_paths: list) -> str:
    """OCR en todos los frames/imágenes. Deduplica texto repetido."""
    if not frame_paths:
        return ""
    try:
        from rapidocr_onnxruntime import RapidOCR
        engine = RapidOCR()
        seen: set = set()
        lines: list = []
        for path in frame_paths:
            result, _ = engine(path)
            if not result:
                continue
            for item in result:
                text = item[1].strip() if len(item) > 1 else ""
                if text and len(text) > 2 and text not in seen:
                    seen.add(text)
                    lines.append(text)
        return "\n".join(lines)
    except ImportError:
        print("  [OCR] Instalá rapidocr-onnxruntime: pip install rapidocr-onnxruntime")
        return ""
    except Exception as e:
        print(f"  [OCR] Error: {e}")
        return ""


def _combine(audio_text: str, frames_text: str) -> str:
    a = (audio_text or "").strip()
    f = (frames_text or "").strip()
    if a and f:
        return f"[Transcripción de voz]\n{a}\n\n[Texto visible en video]\n{f}"
    return f or a


# ── Helpers de audio ──────────────────────────────────────────────────────────

def _get_video_description(url: str) -> str:
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
