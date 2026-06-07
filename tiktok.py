"""
Tiktotext — Transcribe y resume tus colecciones de TikTok a Markdown.

Uso:
    python tiktok.py --setup              # configurar credenciales (primera vez)
    python tiktok.py                      # listar colecciones y elegir una
    python tiktok.py --collection <id>    # procesar colección directamente
    python tiktok.py --liked              # procesar todos los Me gusta
    python tiktok.py --liked --limit 20   # Me gusta, últimos 20
    python tiktok.py --url <url>          # un video suelto (TikTok o YouTube)
"""
import argparse
import sys

# Forzar UTF-8 en la consola de Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _check_setup() -> None:
    from config.settings import is_setup_complete
    if not is_setup_complete():
        print("ERROR: Configuración incompleta.")
        print("  Ejecutá primero: python tiktotex.py --setup\n")
        sys.exit(1)


def _detect_source(url: str) -> str:
    if "tiktok.com" in url:
        return "tiktok"
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    raise ValueError(f"URL no reconocida: {url}")


def _pick_collection() -> tuple[str, str]:
    """Muestra la lista de colecciones y devuelve (id, nombre) elegido por el usuario."""
    from src.url_fetchers import get_tiktok_collections

    collections = get_tiktok_collections()
    if not collections:
        print("No se encontraron colecciones.")
        sys.exit(0)

    print(f"\n{'#':<4} {'Nombre':<35} {'Videos':<8} ID")
    print("-" * 70)
    for i, c in enumerate(collections, 1):
        print(f"{i:<4} {c['name']:<35} {str(c['count']):<8} {c['id']}")

    print()
    choice = input("¿Qué colección querés transcribir? (número o nombre): ").strip()

    # Buscar por número
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(collections):
            return collections[idx]["id"], collections[idx]["name"]

    # Buscar por nombre (case-insensitive, parcial)
    choice_lower = choice.lower()
    matches = [c for c in collections if choice_lower in c["name"].lower()]
    if len(matches) == 1:
        return matches[0]["id"], matches[0]["name"]
    if len(matches) > 1:
        print("  Hay varias coincidencias, sé más específico:")
        for c in matches:
            print(f"    - {c['name']}")
        sys.exit(1)

    print(f"  No se encontró una colección que coincida con '{choice}'.")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tiktotex — TikTok collections to Markdown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--setup",      action="store_true",
                        help="Configurar credenciales de usuario")
    parser.add_argument("--url",        default=None,
                        help="Procesar un video individual (TikTok o YouTube)")
    parser.add_argument("--collection", default=None,
                        help="ID de colección TikTok a procesar")
    parser.add_argument("--liked",      action="store_true",
                        help="Procesar todos los videos con Me gusta")
    parser.add_argument("--limit",      type=int, default=0,
                        help="Máximo de videos a procesar (0 = sin límite)")
    parser.add_argument("--cleanup",    action="store_true",
                        help="Borrar transcripciones .txt cuyo .md ya fue generado")
    args = parser.parse_args()

    # ── Setup ─────────────────────────────────────────────────────────────────
    if args.setup:
        from setup_wizard import run_setup
        run_setup()
        return

    # ── Cleanup de transcripciones ────────────────────────────────────────────
    if args.cleanup:
        from src.processor import cleanup_transcripts
        from config.settings import OUTPUT_DIR
        print(f"Buscando transcripciones .txt aprobadas en: {OUTPUT_DIR}")
        deleted = cleanup_transcripts()
        print(f"\n{deleted} archivo(s) borrado(s).")
        return

    _check_setup()

    from src.processor import process_urls
    from src.state import get_stats

    # ── Video suelto ──────────────────────────────────────────────────────────
    if args.url:
        from src.transcripts import get_tiktok_transcript, get_youtube_transcript
        source = _detect_source(args.url)
        label  = "TikTok" if source == "tiktok" else "YouTube"
        fn     = get_tiktok_transcript if source == "tiktok" else get_youtube_transcript
        print(f"=== {label} — video único ===")
        process_urls([args.url], label, fn)

    # ── Colección específica por ID ────────────────────────────────────────────
    elif args.collection:
        from src.transcripts import get_tiktok_transcript
        from src.url_fetchers import get_tiktok_collection_urls, get_tiktok_collections
        # Buscar el nombre para construir la URL correcta
        collection_name = ""
        for c in get_tiktok_collections():
            if c["id"] == args.collection:
                collection_name = c["name"]
                break
        urls  = get_tiktok_collection_urls(args.collection, collection_name)
        label = f"coleccion_{collection_name or args.collection}"
        if args.limit:
            urls = urls[:args.limit]
            print(f"  Limitado a {args.limit} videos.")
        print(f"=== {label} — {len(urls)} videos ===")
        process_urls(urls, label, get_tiktok_transcript)

    # ── Me gusta ──────────────────────────────────────────────────────────────
    elif args.liked:
        from src.transcripts import get_tiktok_transcript
        from src.url_fetchers import get_tiktok_liked_urls
        urls = get_tiktok_liked_urls()
        if args.limit:
            urls = urls[:args.limit]
            print(f"  Limitado a {args.limit} videos.")
        print(f"=== Me gusta — {len(urls)} videos ===")
        process_urls(urls, "MeGusta", get_tiktok_transcript)

    # ── Flujo interactivo (default) ───────────────────────────────────────────
    else:
        from src.transcripts import get_tiktok_transcript
        from src.url_fetchers import get_tiktok_collection_urls
        collection_id, collection_name = _pick_collection()
        urls  = get_tiktok_collection_urls(collection_id, collection_name)
        label = f"coleccion_{collection_name}"
        if args.limit:
            urls = urls[:args.limit]
        print(f"\n=== {collection_name} — {len(urls)} videos ===")
        process_urls(urls, label, get_tiktok_transcript)

    stats = get_stats()
    print(f"\n=== Registro acumulado: {stats['total']} videos ===")
    for src, count in stats["by_source"].items():
        print(f"  {src}: {count}")


if __name__ == "__main__":
    main()
