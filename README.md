# Tiktotext 🎵→📝

**Convertí tus colecciones de TikTok en conocimiento estructurado — 100% gratis y local.**

Tiktotext descarga la transcripción de texto de los videos de tus colecciones de TikTok, los resume con [Ollama](https://ollama.com/) y los guarda como archivos Markdown listos para usar con cualquier IA.

---

## ¿Para qué sirve?

La idea es simple: guardás en tus **Favoritos/Colecciones de TikTok** los videos sobre temas que te interesan (herramientas de IA, técnicas de código, recetas, tutoriales, etc.). Tiktotext convierte esos videos en documentos de texto estructurados que podés pasarle a tu IA favorita para:

- **Crear prompts** basados en técnicas que viste en un video
- **Explicarle a la IA** un concepto o flujo de trabajo que aprendiste
- **Construir una base de conocimiento** personal a partir de contenido que ya curaste
- **Generar herramientas** a partir de ideas captadas en videos

En lugar de "tengo que acordarme de ese video donde explicaban X", tenés un `.md` con el resumen, los puntos clave y la transcripción completa.

---

## ¿Qué genera por video?

Por cada video procesado se crean dos archivos:

```
~/Desktop/tiktokfav/coleccion_AI/
  20250607_143022_7490612753.md   ← descripción + resumen Ollama (para usar con IA)
  20250607_143022_7490612753.txt  ← transcripción cruda Whisper (para revisar)
```

El `.md` incluye:
- URL del video
- **Descripción original** del video (la que puso el creador)
- Título sugerido por Ollama
- Puntos clave
- Sentimiento general
- Resumen completo

---

## Requisitos

| Herramienta | Instalación |
|-------------|-------------|
| Python 3.10+ | [python.org](https://www.python.org/) |
| Ollama | [ollama.com](https://ollama.com/) |
| Brave o Chrome | Para captura de URLs de TikTok |

> **ffmpeg** se instala automáticamente — no necesitás instalarlo manualmente.

---

## Flujo de trabajo con Claude Code

Si usás **Claude Code** con este proyecto configurado, el flujo más rápido es:

1. Abrís Claude Code en la carpeta del proyecto
2. Escribís `/tiktok` — Claude lista tus colecciones de TikTok y te pide que elijas
3. Elegís una colección (por número o nombre) y Claude ejecuta el pipeline completo

Para un **video suelto de YouTube o TikTok**, simplemente pasale el link a Claude:
> "Procesá este video: https://www.youtube.com/watch?v=..."

Claude invoca `/tiktok` con esa URL, extrae la transcripción y genera el `.md` automáticamente.

El resultado queda en `Desktop/tiktokfav/` listo para usar con cualquier IA.

---

## Instalación

```bash
git clone https://github.com/inversionesdecg-sys/tiktotext.git
cd tiktotext
pip install -r requirements.txt
playwright install chromium
```

> **Nota:** `rapidocr-onnxruntime` descarga sus modelos OCR (~30 MB) la primera vez que se usa un video con imágenes.
> `faster-whisper` descarga el modelo Whisper elegido (~250 MB para `small`) en el primer uso.

Descargá un modelo de Ollama:
```bash
ollama pull mistral
# o cualquier modelo que tengas: llama3, qwen2.5, deepseek-r1, etc.
```

### Dependencias incluidas en requirements.txt

| Paquete | Para qué |
|---------|----------|
| `yt-dlp` | Descargar audio/video/imágenes de TikTok y YouTube |
| `faster-whisper` | Transcripción de voz local (preferido) |
| `openai-whisper` | Transcripción de voz local (fallback) |
| `rapidocr-onnxruntime` | OCR para carruseles y videos con texto en pantalla |
| `imageio[ffmpeg]` | ffmpeg bundled — no requiere instalación global |
| `playwright` | Captura de URLs de colecciones TikTok (headless) |
| `TikTokApi` | Acceso a la API de TikTok |
| `requests` | Llamadas a la API de Ollama |

---

## Configuración (primera vez)

```bash
python tiktok.py --setup
```

El wizard te guía en 7 pasos:
1. Usuario de TikTok (sin `@`)
2. Path a tu browser (Brave o Chrome)
3. Carpeta donde guardar los `.md`
4. Modelo de Ollama
5. Modelo de Whisper (`small` recomendado para español)

Todo se guarda en `~/.tiktotex/config.json`.

### Cookies de TikTok

Exportá tus cookies desde el browser con [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) y guardá el archivo como:

```
~/.tiktotex/tiktok_cookies.txt
```

---

## Uso

### Modo interactivo (recomendado)
```bash
python tiktok.py
```
Muestra tus colecciones y te pide que elijas una.

### Colección por ID
```bash
python tiktok.py --collection 7496486717777627959
```

### Un video suelto
```bash
python tiktok.py --url https://www.tiktok.com/@usuario/video/123456789
```

### Videos con Me gusta
```bash
python tiktok.py --liked
python tiktok.py --liked --limit 20
```

### Borrar transcripciones aprobadas
```bash
python tiktok.py --cleanup
```
Borra los `.txt` crudos cuyo `.md` resumen ya existe y aprobaste.

---

## Cómo funciona

```
TikTok Favoritos / Colecciones
        │
        ▼  Playwright (headless, invisible) captura la petición firmada
        │
        ▼  Python pagina la API con requests
        │
    Lista de URLs
        │
        ├──▶ yt-dlp obtiene descripción del video
        │
        ├──▶ yt-dlp descarga audio (mp3)
        │
        ▼  Whisper transcribe localmente (sin internet)
        │
        ▼  Ollama resume en Markdown (sin internet)
        │
   descripción + resumen → archivo.md
   transcripción cruda   → archivo.txt
```

---

## Modelos de Whisper recomendados

| Modelo | Tamaño | Velocidad | Para español |
|--------|--------|-----------|--------------|
| `tiny` | 39 MB | muy rápido | básico |
| `base` | 74 MB | rápido | bueno |
| `small` | 244 MB | moderado | **recomendado** ✓ |
| `medium` | 769 MB | lento | excelente |

---

## Notas

- Solo funciona con videos en tus **propias** colecciones/favoritos
- El browser abre brevemente (~5 seg) para capturar URLs y luego se cierra solo
- Videos sin voz (solo música) se saltean automáticamente
- El registro en `.processed.json` evita reprocesar videos ya hechos

---

## Licencia

MIT
