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
        self._ensure_env_loaded()

    def _ensure_env_loaded(self) -> None:
        """Ensure .env file is loaded if GROQ_API_KEY is not already in os.environ."""
        if "GROQ_API_KEY" not in os.environ:
            try:
                from dotenv import load_dotenv
                load_dotenv(self.repo_root / ".env")
            except ImportError:
                env_file = self.repo_root / ".env"
                if env_file.exists():
                    with open(env_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                k, v = line.split("=", 1)
                                k, v = k.strip(), v.strip().strip("'\"")
                                if k not in os.environ:
                                    os.environ[k] = v

    def extract_pdf(self, pdf_path: Path) -> str:
        """Extract text from digital PDF using fitz, pypdf, or binary fallback."""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            text_blocks = [page.get_text() for page in doc]
            doc.close()
            txt = "\n".join(text_blocks).strip()
            if txt:
                return txt
        except Exception:
            pass

        try:
            import pypdf
            reader = pypdf.PdfReader(pdf_path)
            txt = "\n".join(p.extract_text() or "" for p in reader.pages).strip()
            if txt:
                return txt
        except Exception:
            pass

        # Fallback reading
        with open(pdf_path, "rb") as f:
            content = f.read().decode("latin1", errors="ignore")
            return content[:2000]

    def extract_image(self, img_path: Path) -> str:
        """Extract text from image using Tesseract CLI / pytesseract, with caching and Groq vision fallback."""
        try:
            with open(img_path, "rb") as f:
                img_bytes = f.read()
            import hashlib
            file_hash = hashlib.sha256(img_bytes).hexdigest()
            cached = self.cache.get_ocr(file_hash, "tesseract")
            if cached and cached.get("extracted_text"):
                return cached["extracted_text"]

            text = ""
            # Try subprocess tesseract CLI first
            try:
                import subprocess
                res = subprocess.run(
                    ["tesseract", str(img_path), "stdout", "--psm", "6"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                text = (res.stdout or "").strip()
            except Exception:
                pass

            # Try pytesseract if subprocess failed
            if not text:
                try:
                    import pytesseract
                    from PIL import Image
                    img = Image.open(img_path)
                    text = pytesseract.image_to_string(img, config="--psm 6").strip()
                except Exception:
                    pass

            if text:
                self.cache.put_ocr(file_hash, "tesseract", str(img_path), text)
                return text

            # Vision model fallback if Tesseract extracted nothing
            vision_text = self._extract_image_vision_fallback(img_bytes, file_hash, str(img_path))
            return vision_text
        except Exception:
            return ""

    def _extract_image_vision_fallback(self, img_bytes: bytes, file_hash: str, file_path: str) -> str:
        """Fallback to Groq vision model when Tesseract fails or yields empty text."""
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            return ""
        try:
            import base64
            b64_img = base64.b64encode(img_bytes).decode("utf-8")
            from groq import Groq
            client = Groq(api_key=api_key)
            prompt = "Extract all visible text, identifiers, account numbers, resource IDs, emails, status codes, and table rows exactly as shown."
            completion = client.chat.completions.create(
                model="llama-3.2-90b-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}}
                        ],
                    }
                ],
                temperature=0.0,
                max_tokens=1500,
            )
            text = completion.choices[0].message.content or ""
            in_tokens = completion.usage.prompt_tokens if completion.usage else 0
            out_tokens = completion.usage.completion_tokens if completion.usage else 0
            self.cache.put_ocr(file_hash, "groq-vision", file_path, text)
            self.cache.put_llm(f"vision:{file_hash}", "llama-3.2-90b-vision-preview", text, None, in_tokens, out_tokens)
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
