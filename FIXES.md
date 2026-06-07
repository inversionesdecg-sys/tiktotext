# Fixes & Mejoras

Registro de correcciones y mejoras aplicadas al proyecto.

---

## [2026-06-07] OCR de imágenes en videos sin voz

### Problema
Videos de TikTok que consisten en imágenes/slides con música de fondo generaban
transcripciones vacías o de una sola palabra ("Música"). Todo el contenido real
estaba en los frames, no en el audio.

Afectaba especialmente:
- Carruseles de TikTok (`/photo/` URLs) — series de imágenes deslizables
- Screen recordings con música de fondo
- Videos tipo "infografía en slides"

### Solución
Se agrega un pipeline secundario basado en OCR de frames:

**Para carruseles (`/photo/` en URL):**
```
URL /photo/ detectada
  → intenta descargar imágenes directas vía yt-dlp (-f Image/mhtml/best)
  → si falla: descarga video slideshow + extrae frames cada 2s (modo denso)
  → OCR con rapidocr-onnxruntime en todas las imágenes
  → deduplica texto repetido entre slides
```

**Para videos con música:**
```
Whisper devuelve < 50 chars (solo música)
  → descarga video en baja resolución
  → extrae frames en timestamps fijos [1, 4, 8, 12, 16, 20, 25, 30, 40, 50]s
  → OCR
```

**Si el video tiene voz Y texto visible:**
```
Resultado = "[Transcripción de voz]\n...\n\n[Texto visible en video]\n..."
```

### Nueva dependencia
```
pip install rapidocr-onnxruntime
```
No requiere instalación de sistema ni PyTorch. ONNX Runtime (~50 MB).

### Archivos modificados
- `src/transcripts.py` — lógica principal

---

## [2026-06-07] Encoding UTF-8 BOM en archivos .md

### Problema
Los archivos `.md` generados mostraban mojibake (caracteres españoles corruptos)
cuando se abrían en Claude Desktop y otras apps de Windows, porque Windows asume
ANSI (cp1252) al no encontrar una señal de encoding.

### Solución
Cambio de `encoding="utf-8"` a `encoding="utf-8-sig"` al escribir los `.md`.
El BOM (`\xEF\xBB\xBF`) al inicio del archivo le indica a Windows que es UTF-8.

### Archivos modificados
- `src/processor.py` — función `_save_markdown()`

---

## [2026-06-07] Auto-inicio de Ollama

### Problema
Si Ollama no estaba corriendo, el pipeline fallaba con `ConnectionRefusedError`
al intentar resumir con el LLM.

### Solución
La función `_ensure_ollama()` en `summarizer.py` detecta si Ollama está caído
y lo lanza automáticamente con `ollama serve` en segundo plano (sin ventana).
Espera hasta 15 segundos a que esté listo.

### Archivos modificados
- `src/summarizer.py` — función `_ensure_ollama()`

---

## [2026-06-07] ffmpeg bundled (sin instalación global)

### Problema
El pipeline fallaba si ffmpeg no estaba instalado en el sistema.

### Solución
Se usa `imageio_ffmpeg.get_ffmpeg_exe()` para obtener el ffmpeg incluido
con el paquete `imageio[ffmpeg]`, sin necesidad de instalación global.

### Nueva dependencia
```
pip install imageio[ffmpeg]
```

### Archivos modificados
- `src/transcripts.py` — función `_ffmpeg_exe()`

---

## [2026-06-07] Descripción del video en el .md

### Problema
Los archivos `.md` no incluían la descripción original del video (lo que puso
el creador), perdiendo contexto valioso.

### Solución
Se agrega una sección `**Descripción del video:**` en el `.md` cuando la
descripción está disponible. Se obtiene vía `yt-dlp --dump-json`.

### Archivos modificados
- `src/transcripts.py` — función `_get_video_description()`
- `src/processor.py` — función `_save_markdown()`

---

## [2026-06-07] Soporte de YouTube

### Mejora
El pipeline ahora acepta URLs de YouTube además de TikTok.
- Descarga subtítulos automáticos/nativos (VTT) como primera opción
- Fallback a Whisper si no hay subtítulos

### Archivos modificados
- `src/transcripts.py` — función `get_youtube_transcript()`
- `tiktok.py` — detección de URL de YouTube

---

## [2026-06-07] Browser headless (sin ventana visible)

### Problema
Brave/Chrome se abría en primer plano al capturar URLs de TikTok, interrumpiendo
el flujo de trabajo del usuario.

### Solución
Playwright se ejecuta con `headless=True` en todas las instancias de captura
de URLs (colecciones y me-gusta).

### Archivos modificados
- `src/url_fetchers.py`
