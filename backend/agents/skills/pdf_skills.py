from __future__ import annotations

import base64
import logging
import os
import time
from typing import Any

from .pdf_models import PDFPageResult

logger = logging.getLogger(__name__)

try:
    import fitz

    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


class PdfToImageSkill:
    def convert(
        self,
        pdf_path: str,
        page_num: int,
        output_dir: str,
        dpi: int = 150,
        min_size: int = 400,
    ) -> dict[str, Any]:
        if not FITZ_AVAILABLE or not PIL_AVAILABLE:
            return {"ok": False, "error": "fitz/PIL not available"}
        if not os.path.exists(pdf_path):
            return {"ok": False, "error": f"PDF not found: {pdf_path}"}
        os.makedirs(output_dir, exist_ok=True)

        doc = fitz.open(pdf_path)
        try:
            if page_num < 1 or page_num > len(doc):
                return {"ok": False, "error": f"Page {page_num} out of range"}

            page = doc[page_num - 1]
            zoom = dpi / 72
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            temp_png = os.path.join(output_dir, f"temp_page_{page_num}.png")
            img_path = os.path.join(output_dir, f"kimi_ocr_page_{page_num}.jpg")
            pix.save(temp_png)

            with Image.open(temp_png) as img:
                width, height = img.size
                if width < min_size and height < min_size:
                    scale = min_size / min(width, height)
                    img = img.resize((int(width * scale), int(height * scale)), Image.LANCZOS)
                img.convert("RGB").save(img_path, format="JPEG", quality=90, optimize=True)
            os.remove(temp_png)
            return {"ok": True, "image_path": img_path}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            doc.close()


class OcrImageSkill:
    def __init__(
        self,
        api_key: str,
        vision_model: str = "moonshot-v1-8k-vision-preview",
        base_url: str = "https://api.moonshot.cn/v1",
        timeout: int = 180,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key
        self.vision_model = vision_model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    def run(
        self,
        image_path: str,
        prompt: str = "请识别图片中的所有文字内容，直接输出文字，不要其他说明。",
    ) -> dict[str, Any]:
        if not HTTPX_AVAILABLE:
            return {"ok": False, "error": "httpx not available"}
        if not os.path.exists(image_path):
            return {"ok": False, "error": f"Image not found: {image_path}"}

        with open(image_path, "rb") as f:
            base64_img = base64.b64encode(f.read()).decode("utf-8")

        payload = {
            "model": self.vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}},
                    ],
                }
            ],
            "max_tokens": 4096,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        url = f"{self.base_url}/chat/completions"

        last_error = "unknown"
        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    return {"ok": True, "text": data["choices"][0]["message"]["content"]}
                last_error = f"{resp.status_code}: {resp.text[:500]}"
            except Exception as e:
                last_error = str(e)
            if attempt < self.max_retries - 1:
                time.sleep(2**attempt)
        return {"ok": False, "error": last_error}


class FormatMarkdownSkill:
    def __init__(
        self,
        api_key: str,
        text_model: str = "moonshot-v1-8k",
        base_url: str = "https://api.moonshot.cn/v1",
        timeout: int = 180,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key
        self.text_model = text_model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    def run(self, ocr_text: str) -> dict[str, Any]:
        if not HTTPX_AVAILABLE:
            return {"ok": False, "error": "httpx not available"}
        system_prompt = """你是文档审查规则提炼专家。你的任务是将OCR识别出的标准文档（如GJB标准、军用文档等）提炼成结构化的审查规则，用于后续agent检查文档内容是否符合要求。

## 输出格式要求
按照以下固定结构输出Markdown：

# **《[文档主题]审查规则》**

**一、审查目的**
[一句话说明该规则用于什么审查]

**二、审查范围**
[说明审查涉及哪些内容]

**三、审查规则**
审查时需逐项核对以下内容，确保符合要求：

**[规则名称1]**
- **a) [子项1]**：[详细说明检查什么]
- **b) [子项2]**：[详细说明检查什么]
- ...

**[规则名称2]**
- ...

**四、审查方法**
1. [方法1描述]
2. [方法2描述]
3. [方法3描述]

**五、不符合处理**
若发现不符合项，需[说明如何处理]

## 内容要求
1. **严格基于原文**：所有规则内容必须来自输入文档，不能添加原文没有的信息
2. **充分展开**：将原文简短的条款展开为详细、可执行的检查项，每个检查项需包含：
   - 检查什么（what）
   - 期望状态或标准（expected）
   - 如何检查（how，可选）
3. **保持编号一致性**：原文的条款编号（如1.、2.、a.、b.、c.）必须保留
4. **直接输出Markdown**：不要代码块包裹，不要添加解释"""
        payload = {
            "model": self.text_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请提炼审查规则：\n\n{ocr_text}"},
            ],
            "max_tokens": 8192,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        url = f"{self.base_url}/chat/completions"

        last_error = "unknown"
        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"].strip()
                    if content.startswith("```"):
                        content = content[3:]
                    if content.endswith("```"):
                        content = content[:-3]
                    return {"ok": True, "text": content.strip()}
                last_error = f"{resp.status_code}: {resp.text[:500]}"
            except Exception as e:
                last_error = str(e)
            if attempt < self.max_retries - 1:
                time.sleep(2**attempt)
        return {"ok": False, "error": last_error}


class ExtractPdfTextSkill:
    def __init__(self, ocr_enabled: bool = True, ocr_language: str = "chi_sim+eng", dpi: int = 300):
        self.ocr_enabled = ocr_enabled
        self.ocr_language = ocr_language
        self.dpi = dpi

    def run(self, page: Any, page_num: int) -> PDFPageResult:
        text = page.extract_text()
        if text and text.strip():
            return PDFPageResult(page_num=page_num, text=text, method="text")
        if not self.ocr_enabled:
            return PDFPageResult(page_num=page_num, text="", method="none", warnings=["OCR disabled"])
        try:
            import pytesseract

            configured_cmd = os.environ.get("TESSERACT_CMD")
            if configured_cmd and os.path.exists(configured_cmd):
                pytesseract.pytesseract.tesseract_cmd = configured_cmd
            else:
                for default_cmd in (
                    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                ):
                    if os.path.exists(default_cmd):
                        pytesseract.pytesseract.tesseract_cmd = default_cmd
                        break

            img = page.to_image(resolution=self.dpi)
            ocr_text = pytesseract.image_to_string(img.original, lang=self.ocr_language).strip()
            return PDFPageResult(
                page_num=page_num,
                text=ocr_text,
                method="ocr" if ocr_text else "none",
                warnings=[] if ocr_text else ["OCR returned empty text"],
            )
        except Exception as e:
            logger.warning("OCR failed on page %s: %s", page_num, str(e))
            return PDFPageResult(page_num=page_num, text="", method="none", error=str(e))
