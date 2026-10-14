"""
Ollama extraction module using Gemma 3n 2B with structured outputs,
retry logic, and self-consistency k-sample generation.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, List, Optional

import ollama
from src.schema.invoice import InvoiceExtraction, ParsedDoc, RawExtraction

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemma3n:e2b"
DEFAULT_ENDPOINT = "http://localhost:11434"
DEFAULT_PROMPT_PATH = Path("prompts/extract_v1.txt")


def load_system_prompt(prompt_path: Path = DEFAULT_PROMPT_PATH) -> str:
    """Load system prompt from file, fallback to built-in prompt."""
    if prompt_path.is_file():
        return prompt_path.read_text(encoding="utf-8").strip()
    return (
        "You are an expert document information extraction system.\n"
        "Extract structured invoice and receipt information from the provided OCR document text.\n"
        "Return ONLY the fields specified in the JSON schema. Do not perform math or alter numbers."
    )


def extract_invoice(
    parsed: ParsedDoc,
    k_samples: int = 0,
    model: str = DEFAULT_MODEL,
    endpoint: str = DEFAULT_ENDPOINT,
    prompt_path: Path = DEFAULT_PROMPT_PATH,
    max_retries: int = 2,
    client: Optional[Any] = None,
) -> RawExtraction:
    """
    Extract structured receipt/invoice data from a ParsedDoc using Ollama.

    Args:
        parsed: ParsedDoc object containing markdown text.
        k_samples: Number of consistency samples to generate at temperature 0.7.
        model: Ollama model identifier (default: 'gemma3n:e2b').
        endpoint: Ollama host endpoint (default: 'http://localhost:11434').
        prompt_path: Path to system prompt text file.
        max_retries: Number of retries on JSON/schema parse failure (default: 2).
        client: Optional pre-configured Ollama client (for mocking / dependency injection).

    Returns:
        RawExtraction containing primary extraction, timing, token counts, and status.
    """
    if client is None:
        client = ollama.Client(host=endpoint)

    system_prompt = load_system_prompt(Path(prompt_path))
    schema = InvoiceExtraction.model_json_schema()

    user_message = (
        f"Document Text:\n"
        f"```\n"
        f"{parsed.text}\n"
        f"```\n\n"
        f"Extract the invoice/receipt information adhering strictly to the JSON schema."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    t0 = time.perf_counter()
    primary_extraction: Optional[InvoiceExtraction] = None
    raw_response_text = ""
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    status = "failed"

    # Primary extraction with up to max_retries retries
    current_messages = list(messages)
    for attempt in range(1 + max_retries):
        try:
            logger.info("Extracting %s (attempt %d/%d)", parsed.doc_id, attempt + 1, 1 + max_retries)
            response = client.chat(
                model=model,
                messages=current_messages,
                format=schema,
                options={
                    "temperature": 0.0,
                    "seed": 42,
                    "num_ctx": 8192,
                },
            )

            raw_response_text = response.message.content or ""
            prompt_tokens = getattr(response, "prompt_eval_count", None)
            completion_tokens = getattr(response, "eval_count", None)

            # Validate against Pydantic schema
            parsed_json = json.loads(raw_response_text)
            primary_extraction = InvoiceExtraction.model_validate(parsed_json)
            status = "ok"
            break

        except (json.JSONDecodeError, Exception) as exc:
            logger.warning(
                "Extraction failed on attempt %d for doc %s: %s",
                attempt + 1,
                parsed.doc_id,
                exc,
            )
            if attempt < max_retries:
                # Add retry feedback message
                current_messages = list(messages) + [
                    {"role": "assistant", "content": raw_response_text},
                    {
                        "role": "user",
                        "content": (
                            f"The previous output failed validation: {exc}. "
                            f"Please output strictly valid JSON conforming exactly to the schema."
                        ),
                    },
                ]
            else:
                logger.error("All %d extraction attempts failed for doc %s", 1 + max_retries, parsed.doc_id)

    if primary_extraction is None:
        primary_extraction = InvoiceExtraction()

    # Generate k consistency samples if requested and primary succeeded
    samples: List[InvoiceExtraction] = []
    if k_samples > 0 and status == "ok":
        for i in range(k_samples):
            try:
                sample_resp = client.chat(
                    model=model,
                    messages=messages,
                    format=schema,
                    options={
                        "temperature": 0.7,
                        "seed": 42 + i + 1,
                        "num_ctx": 8192,
                    },
                )
                sample_raw = sample_resp.message.content or ""
                sample_json = json.loads(sample_raw)
                sample_item = InvoiceExtraction.model_validate(sample_json)
                samples.append(sample_item)
            except Exception as e:
                logger.warning("Consistency sample %d failed for doc %s: %s", i + 1, parsed.doc_id, e)

    extract_seconds = round(time.perf_counter() - t0, 3)

    return RawExtraction(
        doc_id=parsed.doc_id,
        primary=primary_extraction,
        samples=samples,
        raw_response=raw_response_text,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        extract_seconds=extract_seconds,
        status=status,
    )
