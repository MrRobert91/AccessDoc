# AccessDoc

Automatic PDF accessibility remediation powered by Gemma 4.
Produces PDF/UA-1 (ISO 14289) and WCAG 2.1 AA compliant documents.

## Quick Start

```bash
# 1. Clone and configure
git clone https://github.com/MrRobert91/AccessDoc
cd AccessDoc
cp .env.example .env
# Edit .env: add your OPENROUTER_API_KEY

# 2. Start everything (Docker)
docker compose up --build

# 3. Open the app
open http://localhost:3000
```

## What it fixes

| Issue | WCAG Criterion | Method |
|---|---|---|
| Missing image alt text | 1.1.1 | Gemma 4 Vision generates descriptive text |
| Untagged headings | 1.3.1 | Font size analysis + AI classification |
| Wrong reading order | 1.3.2 | Column detection + AI layout analysis |
| No bookmarks | 2.4.1 | Auto-generated from heading hierarchy |
| No document title | 2.4.2 | Extracted from first H1 |
| No language | 3.1.1 | Auto-detected by Gemma 4 |
| No semantic tags | 4.1.2 | Full PDF/UA-1 tag tree built |

## Architecture

```
Next.js 15 → FastAPI → Gemma 4 (OpenRouter) → pikepdf → veraPDF
```

### Tech Stack

- **Frontend**: Next.js 15, TypeScript, Tailwind CSS
- **Backend**: FastAPI, Python 3.12, uvicorn
- **PDF Processing**: PyMuPDF, pdfplumber, pikepdf
- **AI**: Gemma 4 (31B-IT / 26B-A4B-IT) via OpenRouter API
- **Validation**: veraPDF CLI (ISO 14289-1 / PDF/UA-1)
- **Progress**: Server-Sent Events (SSE)

## Development

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
OPENROUTER_API_KEY=... uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev    # http://localhost:3000

# Tests
cd backend && OPENROUTER_API_KEY=test pytest -q    # 76 tests
cd frontend && npm test                             # 16 tests
```

### Environment variables

Backend:
- `OPENROUTER_API_KEY` (required)
- `GEMMA_MODEL_ACCURATE`, `GEMMA_MODEL_FAST`
- `MAX_FILE_SIZE_MB`, `JOB_TTL_HOURS`
- `VERAPDF_PATH`, `TMP_DIR`
- `CORS_ORIGINS` (JSON array)

Frontend:
- `NEXT_PUBLIC_API_URL` — full base including `/api/v1`
  (e.g. `http://localhost:8000/api/v1`)

## License

Creative Commons Attribution 4.0 — see [LICENSE](./LICENSE).
