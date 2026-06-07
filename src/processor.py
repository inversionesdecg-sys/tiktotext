"""
Procesa videos en paralelo usando asyncio.
PARALLEL_WORKERS workers corren simultáneamente: cada uno descarga audio,
transcribe con Whisper, resume con Ollama y guarda el .md + .txt.

Flujo de aprobación:
  - El transcript crudo se guarda como {nombre}.txt junto al {nombre}.md
  - Una vez que aprobás los resúmenes, corrés: python tiktok.py --cleanup
  - --cleanup borra todos los .txt cuyo .md ya existe (resumen listo)
"""
import asyncio
import glob
import os
from datetime import datetime
from config.settings import OUTPUT_DIR, PARALLEL_WORKERS
from src.summarizer import summarize
from src.state import is_processed, mark_processed


def process_urls(urls: list[str], source: str, get_transcript_fn) -> dict:
    """
    Procesa todas las URLs en paralelo con PARALLEL_WORKERS workers simultáneos.
    get_transcript_fn debe devolver (text: str, description: str).
    """
    return asyncio.run(_process_all(urls, source, get_transcript_fn))


async def _process_all(urls: list[str], source: str, get_transcript_fn) -> dict:
    folder  = os.path.join(OUTPUT_DIR, source)
    total   = len(urls)
    counts  = {"processed": 0, "skipped": 0, "errors": 0}
    lock    = asyncio.Lock()
    sem     = asyncio.Semaphore(PARALLEL_WORKERS)

    print(f"  Procesando {total} videos con {PARALLEL_WORKERS} workers paralelos.")

    async def handle(i: int, url: str):
        async with sem:
            print(f"\n[{source}] {i}/{total}: {url}")

            if is_processed(url):
                print("  Ya procesado, saltando.")
                async with lock:
                    counts["skipped"] += 1
                return

            try:
                if asyncio.iscoroutinefunction(get_transcript_fn):
                    result = await get_transcript_fn(url)
                else:
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(None, get_transcript_fn, url)
                # Soporta (text, description) o solo text
                if isinstance(result, tuple):
                    text, description = result
                else:
                    text, description = result, ""
            except Exception as e:
                print(f"  Error al transcribir: {e}")
                async with lock:
                    counts["errors"] += 1
                return

            if not text or len(text) < 20:
                print("  Transcripción vacía o insuficiente, saltando.")
                async with lock:
                    counts["errors"] += 1
                return

            try:
                summary = await asyncio.get_running_loop().run_in_executor(
                    None, summarize, text
                )
            except Exception as e:
                print(f"  Error al resumir: {e}")
                async with lock:
                    counts["errors"] += 1
                return

            filename = _make_filename(url)
            _save_markdown(folder, filename, url, description, summary)
            _save_transcript(folder, filename, text)
            mark_processed(url, filename, source)
            async with lock:
                counts["processed"] += 1

    await asyncio.gather(*[handle(i, url) for i, url in enumerate(urls, 1)])

    print(
        f"\n[{source}] Listo - "
        f"nuevos: {counts['processed']}, "
        f"saltados: {counts['skipped']}, "
        f"errores: {counts['errors']}"
    )
    return counts


def cleanup_transcripts(source: str = "") -> int:
    """
    Borra los archivos .txt cuyo .md correspondiente ya existe.
    Devuelve la cantidad de archivos borrados.
    """
    base = os.path.join(OUTPUT_DIR, source) if source else OUTPUT_DIR
    pattern = os.path.join(base, "**", "*.txt")
    txt_files = glob.glob(pattern, recursive=True)

    deleted = 0
    for txt_path in txt_files:
        md_path = txt_path[:-4] + ".md"
        if os.path.exists(md_path):
            os.remove(txt_path)
            print(f"  Borrado: {txt_path}")
            deleted += 1
        else:
            print(f"  Sin .md aún, conservado: {txt_path}")

    return deleted


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_filename(url: str) -> str:
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    slug = url.rstrip("/").split("/")[-1][:60]
    return f"{date_str}_{slug}.md"


def _save_markdown(folder: str, filename: str, url: str, description: str, summary: str):
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, filename)
    desc_section = f"\n**Descripción del video:**\n{description}\n" if description else ""
    with open(filepath, "w", encoding="utf-8-sig") as f:
        f.write(f"# Resumen\n\n**URL:** {url}\n{desc_section}\n---\n\n{summary}\n")
    print(f"  Guardado: {filepath}")


def _save_transcript(folder: str, md_filename: str, text: str):
    txt_filename = md_filename[:-3] + ".txt"
    filepath = os.path.join(folder, txt_filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)
