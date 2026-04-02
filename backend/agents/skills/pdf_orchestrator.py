from __future__ import annotations

import os
import time
from typing import Optional

from .pdf_models import PDFParseRequest, PDFParseResult
from .pdf_skills import ExtractPdfTextSkill, FormatMarkdownSkill, OcrImageSkill, PdfToImageSkill

try:
    import pdfplumber

    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False


class PDFParseOrchestrator:
    def __init__(
        self,
        extract_text_skill: ExtractPdfTextSkill,
        pdf_to_image_skill: PdfToImageSkill,
        ocr_image_skill: Optional[OcrImageSkill],
        format_markdown_skill: Optional[FormatMarkdownSkill],
        temp_dir: str,
    ) -> None:
        self.extract_text_skill = extract_text_skill
        self.pdf_to_image_skill = pdf_to_image_skill
        self.ocr_image_skill = ocr_image_skill
        self.format_markdown_skill = format_markdown_skill
        self.temp_dir = temp_dir

    def parse(self, req: PDFParseRequest) -> PDFParseResult:
        if not PDFPLUMBER_AVAILABLE:
            raise ImportError("pdfplumber is required for PDF parsing")
        if not os.path.exists(req.pdf_path):
            raise FileNotFoundError(f"PDF file not found: {req.pdf_path}")
        if req.start_page is not None and req.start_page < 1:
            raise ValueError("start_page must be >= 1")
        if req.end_page is not None and req.end_page < 1:
            raise ValueError("end_page must be >= 1")
        if req.start_page is not None and req.end_page is not None and req.start_page > req.end_page:
            raise ValueError("start_page cannot be greater than end_page")

        result = PDFParseResult()
        with pdfplumber.open(req.pdf_path) as pdf:
            result.page_count = len(pdf.pages)
            start = max(1, req.start_page or 1)
            end = min(req.end_page or result.page_count, result.page_count)
            if start > result.page_count:
                raise ValueError(f"start_page out of range: {start} > page_count {result.page_count}")
            if end < 1:
                raise ValueError("end_page out of range")

            for page_num in range(start, end + 1):
                started = time.time()
                page_result = self.extract_text_skill.run(pdf.pages[page_num - 1], page_num)

                if req.use_kimi_ocr and self.ocr_image_skill:
                    image_ret = self.pdf_to_image_skill.convert(req.pdf_path, page_num, self.temp_dir)
                    if image_ret.get("ok"):
                        image_path = image_ret["image_path"]
                        ocr_ret = self.ocr_image_skill.run(image_path=image_path)
                        try:
                            os.remove(image_path)
                        except OSError:
                            pass
                        if ocr_ret.get("ok"):
                            page_result.text = ocr_ret.get("text", "")
                            page_result.method = "kimi-ocr"
                            if req.format_markdown and self.format_markdown_skill and page_result.text.strip():
                                format_ret = self.format_markdown_skill.run(page_result.text)
                                if format_ret.get("ok"):
                                    page_result.text = format_ret.get("text", "")
                                    page_result.method = "kimi-ocr-markdown"
                                else:
                                    page_result.warnings.append(
                                        f"Markdown format failed: {format_ret.get('error')}",
                                    )
                        else:
                            page_result.warnings.append(f"Kimi OCR failed: {ocr_ret.get('error')}")
                    else:
                        page_result.warnings.append("Kimi OCR skipped due to image conversion failure")
                        page_result.error = image_ret.get("error")

                page_result.metrics["duration_ms"] = int((time.time() - started) * 1000)
                result.pages.append(page_result)
                result.text += f"\n--- Page {page_num} ---\n{page_result.text}"
                if not page_result.text.strip():
                    result.warnings.append(f"Page {page_num} has no extracted text")

        return result
