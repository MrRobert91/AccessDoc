import os
import json
import pytest
import respx
from httpx import Response

from app.services.analysis.gemma_client import GemmaClient


@pytest.mark.asyncio
async def test_accurate_model_id():
    client = GemmaClient(model_size="accurate")
    assert "31b" in client.model_name or "31B" in client.model_name


@pytest.mark.asyncio
async def test_fast_model_id():
    client = GemmaClient(model_size="fast")
    assert "26b" in client.model_name or "a4b" in client.model_name


@pytest.mark.asyncio
@respx.mock
async def test_analyze_page_structure_parses_json_response():
    fake_response = {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "google/gemma-4-31b-it:free",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": json.dumps({
                        "page_num": 0,
                        "language": "es",
                        "has_multiple_columns": False,
                        "blocks": [
                            {
                                "id": "p0_b0",
                                "role": "H1",
                                "text": "Informe Anual",
                                "level": 1,
                                "is_decorative": False,
                                "alt_text_needed": False,
                                "surrounding_text": "",
                                "reading_order_position": 0,
                                "was_changed": True,
                                "confidence": 0.95,
                            }
                        ],
                    }),
                },
                "finish_reason": "stop",
            }
        ],
    }
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(200, json=fake_response)
    )

    client = GemmaClient(model_size="accurate")
    result = await client.analyze_page_structure(
        page_image_bytes=b"\x89PNG\r\n\x1a\n",
        extracted_text="Informe Anual",
        page_num=0,
    )
    assert result["page_num"] == 0
    assert result["language"] == "es"
    assert result["blocks"][0]["role"] == "H1"


@pytest.mark.asyncio
@respx.mock
async def test_analyze_page_returns_empty_blocks_on_invalid_json():
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0,
            "model": "m",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "not-json-at-all"},
                "finish_reason": "stop",
            }],
        })
    )
    client = GemmaClient(model_size="fast")
    result = await client.analyze_page_structure(
        page_image_bytes=b"\x89PNG", extracted_text="", page_num=2
    )
    assert result["page_num"] == 2
    assert result["blocks"] == []


@pytest.mark.asyncio
@respx.mock
async def test_generate_alt_text_returns_string():
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0,
            "model": "m",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Gráfico de barras mostrando ingresos por trimestre.",
                },
                "finish_reason": "stop",
            }],
        })
    )
    client = GemmaClient(model_size="fast")
    alt = await client.generate_alt_text(
        image_bytes=b"\x89PNG",
        surrounding_text="Ingresos trimestrales",
        language="es",
    )
    assert "Gráfico" in alt or "gr" in alt.lower()


@pytest.mark.asyncio
@respx.mock
async def test_fix_accessibility_issues_returns_structure():
    corrected = {"pages": [{"page_num": 0, "language": "es", "blocks": []}]}
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0,
            "model": "m",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": json.dumps(corrected)},
                "finish_reason": "stop",
            }],
        })
    )
    client = GemmaClient(model_size="accurate")
    result = await client.fix_accessibility_issues(
        document_structure={"pages": [{"page_num": 0, "blocks": []}]},
        failures=[{"rule_id": "1.2.1", "description": "missing alt"}],
    )
    assert "pages" in result
