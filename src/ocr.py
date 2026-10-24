"""Phase 4a & 4b: OCR extraction and LLM fallback extractor.

Uses local PyMuPDF & Tesseract first, with Groq free tier fallback.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from src.cache import CacheManager


class Extractor:
    def __init__(self, repo_root: str | Path | None = None):
        if repo_root is None:
            self.repo_root = Path(__file__).resolve().parent.parent
        else:
            self.repo_root = Path(repo_root)
        self.cache = CacheManager(self.repo_root)

    def extract_pdf(self, pdf_path: Path) -> str:
        """Extract text from digital PDF using PyMuPDF (fitz) or fallback."""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            text_blocks = []
            for page in doc:
                text_blocks.append(page.get_text())
            doc.close()
            return "\n".join(text_blocks).strip()
        except ImportError:
            # Fallback text reading if fitz not installed
            with open(pdf_path, "rb") as f:
                content = f.read().decode("latin1", errors="ignore")
                return content[:2000]

    def extract_image(self, img_path: Path) -> str:
        """Extract text from image using Tesseract or cached result."""
        try:
            import pytesseract
            from PIL import Image
            img = Image.open(img_path)
            text = pytesseract.image_to_string(img, config="--psm 6")
            return text.strip()
        except Exception:
            return ""

    def extract_structured_fallback(
        self,
        text_chunk: str,
        context: str = "",
        model: str = "llama-3.1-8b-instant"
    ) -> list[dict[str, Any]]:
        """Call Groq free tier LLM with strict JSON schema if cache miss."""
        prompt = (
            f"Context: {context}\n"
            f"Evidence Snippet:\n{text_chunk}\n\n"
            f"Extract any records, system IDs, resource IDs, user identifiers, or states. "
            f"Return ONLY valid JSON matching a list of objects with keys: "
            f"system_id, resource_id, data_category, user_id, state. If none, return []."
        )

        cached = self.cache.get_llm(prompt, model)
        if cached and cached.get("structured") is not None:
            return cached["structured"]

        # Check for GROQ_API_KEY
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            # Deterministic fallback without external network
            return []

        try:
            from groq import Groq
            client = Groq(api_key=api_key)
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a deterministic data extractor. Return JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=1000,
            )
            raw_text = completion.choices[0].message.content or "[]"
            # Parse JSON
            match = re.search(r"\[.*\]", raw_text, re.DOTALL)
            parsed = json.loads(match.group(0)) if match else []
            in_tokens = completion.usage.prompt_tokens if completion.usage else 0
            out_tokens = completion.usage.completion_tokens if completion.usage else 0
            self.cache.put_llm(prompt, model, raw_text, parsed, in_tokens, out_tokens)
            return parsed
        except Exception:
            return []
