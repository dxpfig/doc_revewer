from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class PDFParseRequest:
    pdf_path: str
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    use_kimi_ocr: Optional[bool] = None
    format_markdown: Optional[bool] = None


@dataclass
class PDFPageResult:
    page_num: int
    text: str = ""
    method: str = "none"
    error: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class PDFParseResult:
    text: str = ""
    page_count: int = 0
    pages: list[PDFPageResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "page_count": self.page_count,
            "pages": [asdict(page) for page in self.pages],
            "warnings": self.warnings,
        }
