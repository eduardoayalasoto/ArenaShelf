# Arena Shelf - Biblioteca Digital (Django)

Aplicación web en Django para publicar libros digitales (PDF/EPUB) con:
- Catálogo visual en tarjetas 4:3.
- Upload de archivo + título + autor.
- Validación de tipo/estructura y antivirus (ClamAV).
- Guardado del archivo como BLOB en SQLite.
- Enriquecimiento de metadata con IA (OpenAI).
- Descarga con nombre normalizado `autor-libro.ext`.

## Requisitos
- Python 3.11+
- ClamAV daemon escuchando en `127.0.0.1:3310` (o variables `CLAMD_HOST/CLAMD_PORT`)

## Instalación
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Variables de entorno
```bash
set OPENAI_API_KEY=tu_api_key
set OPENAI_MODEL=gpt-4.1-mini
set CLAMD_HOST=127.0.0.1
set CLAMD_PORT=3310
set CLAMD_STRICT=0
set DJANGO_DEBUG=1
```

## Inicializar DB y correr
```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Worker de procesamiento (scan + IA)
En otra terminal:
```bash
python manage.py run_library_worker
```

Procesar solo un job:
```bash
python manage.py run_library_worker --once
```

## Endpoints
- `GET /` catálogo
- `GET /upload` formulario
- `POST /upload` alta de libro
- `GET /books/<id>` detalle
- `GET /books/<id>/download` descarga
- `GET /api/books` API de listado con filtros `q`, `genre`, `language`, `tag`

## Notas
- `.zip` se bloquea explícitamente; `.epub` se valida como ZIP con `mimetype=application/epub+zip`.
- Si OpenAI falla o no hay API key, se usa fallback con metadata mínima.
- Si `CLAMD_STRICT=1` y ClamAV no está disponible, el libro se rechaza.
