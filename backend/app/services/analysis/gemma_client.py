import asyncio
import base64
import json

import httpx
import structlog
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError

from app.config import settings

log = structlog.get_logger()


STRUCTURE_SYSTEM_PROMPT = """
You are a PDF accessibility expert specializing in PDF/UA-1 (ISO 14289) and WCAG 2.1 AA.
Your task is to analyze PDF document pages and classify every content block with the correct semantic role.

CRITICAL RULES:
1. Classify EVERY visible element on the page
2. A document must have exactly ONE H1 (the document main title)
3. Heading levels must NOT skip (H1→H3 without H2 is an error)
4. Page headers, footers, page numbers = "Artifact" (not content)
5. Logos, decorative lines, ornamental elements = "Artifact"
6. Images with information: role="Figure", is_decorative=false
7. Purely decorative images: role="Figure", is_decorative=true
8. Reading order in multi-column documents: left column first, then right
9. Respond ONLY with valid JSON, no additional text
""".strip()


ALT_TEXT_SYSTEM_PROMPT = """
You are a digital accessibility expert. Generate high-quality alternative text for images in PDF documents, following WCAG 2.1 criterion 1.1.1.

QUALITY PRINCIPLES:
1. Describe the INFORMATION the image conveys, not its visual appearance
2. For charts/graphs: include key data values and the main trend
3. For tables as images: transcribe the most important data
4. For photos: describe the action or situation relevant to the document
5. For logos: "[Company name] logo"
6. NEVER start with "Image of..." or "Photo of..."
7. Maximum 150 words for complex content
8. If purely decorative (line, background, ornamental icon): respond exactly "decorative"
9. Respond in the language specified
""".strip()


class GemmaClient:
    _RETRY_DELAYS = [4, 8, 16]  # seconds between attempts (3 retries after initial)

    def __init__(self, model_size: str = "accurate"):
        self.client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            default_headers={
                "HTTP-Referer": "https://accessdoc.app",
                "X-Title": "AccessDoc - PDF Accessibility",
            },
            timeout=httpx.Timeout(
                connect=30.0,
                read=settings.api_read_timeout,
                write=30.0,
                pool=30.0,
            ),
            max_retries=0,  # retries handled manually with backoff
        )
        self.model_name = (
            settings.gemma_model_accurate
            if model_size == "accurate"
            else settings.gemma_model_fast
        )

    async def _request_with_retry(self, **kwargs) -> str:
        """Call OpenRouter API with exponential backoff on stream/timeout errors."""
        last_exc: Exception | None = None
        for attempt in range(len(self._RETRY_DELAYS) + 1):
            try:
                response = await self.client.chat.completions.create(**kwargs)
                return response.choices[0].message.content or ""
            except (APITimeoutError, APIConnectionError) as exc:
                last_exc = exc
                log.warning(
                    "gemma_stream_timeout_retry",
                    attempt=attempt + 1,
                    max_attempts=len(self._RETRY_DELAYS) + 1,
                    error=str(exc),
                )
                if attempt < len(self._RETRY_DELAYS):
                    await asyncio.sleep(self._RETRY_DELAYS[attempt])
        raise last_exc  # type: ignore[misc]

    async def analyze_page_structure(
        self,
        page_image_bytes: bytes,
        extracted_text: str,
        page_num: int,
    ) -> dict:
        image_b64 = base64.b64encode(page_image_bytes).decode()
        prompt = f"""
Analyze this PDF page (page {page_num + 1}).

EXTRACTED TEXT (with font information when available):
{extracted_text[:3000]}

Classify each visible content block and determine the correct reading order.

Respond with this exact JSON structure:
{{
  "page_num": {page_num},
  "language": "es|en|fr|de|pt",
  "has_multiple_columns": false,
  "blocks": [
    {{
      "id": "p{page_num}_b0",
      "role": "H1|H2|H3|P|Figure|Table|L|LI|LBody|Caption|Artifact|...",
      "text": "block text content",
      "level": 1,
      "is_decorative": false,
      "alt_text_needed": false,
      "surrounding_text": "nearby text for context",
      "reading_order_position": 0,
      "was_changed": true,
      "confidence": 0.95
    }}
  ]
}}
""".strip()

        try:
            raw = await self._request_with_retry(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": STRUCTURE_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_b64}",
                                    "detail": "high",
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    },
                ],
                temperature=0.1,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            log.warning("gemma_request_failed", page=page_num, error=str(e))
            return {"page_num": page_num, "language": "es", "blocks": []}

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            log.warning("gemma_json_parse_failed", raw=raw[:200])
            return {"page_num": page_num, "language": "es", "blocks": []}

    async def generate_alt_text(
        self,
        image_bytes: bytes,
        surrounding_text: str,
        language: str = "es",
    ) -> str:
        image_b64 = base64.b64encode(image_bytes).decode()
        prompt = f"""
Generate alternative text for this image.

LANGUAGE: {language}
SURROUNDING TEXT: "{surrounding_text[:500]}"

If decorative, respond exactly: "decorative"
If informative, generate appropriate descriptive alt text.
""".strip()

        try:
            content = await self._request_with_retry(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": ALT_TEXT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_b64}",
                                    "detail": "high",
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    },
                ],
                temperature=0.3,
                max_tokens=300,
            )
        except Exception as e:
            log.warning("alt_text_request_failed", error=str(e))
            return "decorative"

        return content.strip()

    async def fix_accessibility_issues(
        self,
        document_structure: dict,
        failures: list[dict],
    ) -> dict:
        structure_json = json.dumps(
            document_structure, ensure_ascii=False, indent=2
        )[:8000]
        failures_json = json.dumps(failures, ensure_ascii=False, indent=2)
        prompt = f"""
The following accessibility criteria fail in the generated PDF.
Return the corrected structure JSON that fixes these specific issues.

CURRENT STRUCTURE:
{structure_json}

VALIDATION FAILURES:
{failures_json}

Respond ONLY with the corrected structure JSON.
""".strip()

        try:
            raw = await self._request_with_retry(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=8192,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            log.warning("fix_request_failed", error=str(e))
            return document_structure

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return document_structure
