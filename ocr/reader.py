from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import easyocr
import numpy as np
from PIL import Image, ImageOps

from ocr.parser import ParsedOntLabel, parse_ont_label


class OntOcrReader:
    def __init__(self, languages: list[str], gpu: bool = False):
        self.languages = languages
        self.gpu = gpu
        self._reader: easyocr.Reader | None = None
        self._lock = asyncio.Lock()

    async def read_label(self, image_path: Path) -> ParsedOntLabel:
        return await asyncio.to_thread(self._read_label_sync, image_path)

    def _get_reader(self) -> easyocr.Reader:
        if self._reader is None:
            logging.info("Loading EasyOCR reader languages=%s gpu=%s", self.languages, self.gpu)
            self._reader = easyocr.Reader(self.languages, gpu=self.gpu)
        return self._reader

    def _read_label_sync(self, image_path: Path) -> ParsedOntLabel:
        image = preprocess_image(image_path)
        results = self._get_reader().readtext(
            image,
            detail=1,
            paragraph=False,
            decoder="greedy",
            batch_size=1,
            allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789:/.-() ",
        )
        words: list[str] = []
        confidences: list[float] = []
        for _, text, confidence in results:
            if text and text.strip():
                words.append(text.strip())
                confidences.append(float(confidence))
        raw_text = "\n".join(words)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        parsed = parse_ont_label(raw_text, avg_confidence)
        logging.info(
            "OCR parsed image=%s serial=%s model=%s vendor=%s confidence=%.2f",
            image_path,
            parsed.serial_number,
            parsed.model,
            parsed.manufacturer,
            parsed.confidence,
        )
        return parsed


def preprocess_image(image_path: Path) -> np.ndarray:
    with Image.open(image_path) as pil_image:
        pil_image = ImageOps.exif_transpose(pil_image)
        pil_image = pil_image.convert("RGB")
        max_side = 1800
        width, height = pil_image.size
        scale = min(1.0, max_side / max(width, height))
        if scale < 1.0:
            pil_image = pil_image.resize(
                (int(width * scale), int(height * scale)),
                Image.Resampling.LANCZOS,
            )
        return np.array(pil_image)
