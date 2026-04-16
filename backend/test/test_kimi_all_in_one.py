"""
Kimi OCR + 格式化 + 总结 一体化脚本
PDF -> 图片 -> OCR 识别 -> 大模型格式化 Markdown -> 章节要点总结
"""
import base64
import os
import httpx
from PIL import Image
import fitz
import time

# 配置
KIMI_API_KEY = "sk-tukbjrbeaxDKcsTyDIhGPB7zbO08Nd0BeVgIdAGJtURs9FpG"
KIMI_VISION_MODEL = "moonshot-v1-8k-vision-preview"  # Kimi 视觉模型（OCR）
KIMI_TEXT_MODEL = "moonshot-v1-8k"  # Kimi 文本模型（格式化/总结）

# 测试文件
TEST_PDF = "/mnt/d/WSL/file/软件开发文档通用要求-测试版.pdf"
# 输出到 /home/figodxp/tmp，使用类似 UUID 的格式
import uuid
OUTPUT_DIR = f"/home/figodxp/tmp/import_{uuid.uuid4().hex[:8]}"
MAX_RETRIES = 5


def pdf_to_image_pymupdf(pdf_path, page_num, output_dir, dpi=150, min_size=400):
    """使用 PyMuPDF 将 PDF 转为 JPEG 图片"""
    doc = fitz.open(pdf_path)
    if page_num > len(doc):
        return None

    page = doc[page_num - 1]
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)

    temp_png = os.path.join(output_dir, f"temp_page_{page_num}.png")
    pix.save(temp_png)

    img_path = os.path.join(output_dir, f"kimi_ocr_page_{page_num}.jpg")
    with Image.open(temp_png) as img:
        width, height = img.size
        if width < min_size and height < min_size:
            scale = min_size / min(width, height)
            new_size = (int(width * scale), int(height * scale))
            img = img.resize(new_size, Image.LANCZOS)
        img = img.convert('RGB')
        img.save(img_path, format='JPEG', quality=90, optimize=True)

    os.remove(temp_png)
    doc.close()
    return img_path


def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_image_size(image_path):
    return os.path.getsize(image_path) / 1024


def ocr_image(image_path):
    """OCR 识别图片中的文字，带重试机制"""
    base64_img = encode_image(image_path)
    img_size = get_image_size(image_path)

    print(f"  图片大小: {img_size:.1f} KB")

    url = "https://api.moonshot.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {KIMI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": KIMI_VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请识别图片中的所有文字内容，直接输出文字，不要其他说明。"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                ]
            }
        ],
        "max_tokens": 4096
    }

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            with httpx.Client(timeout=180) as client:
                response = client.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    last_error = f"错误 {response.status_code}: {response.text[:500]}"
        except Exception as e:
            last_error = str(e)

        if attempt < MAX_RETRIES - 1:
            wait_time = 2 ** attempt
            print(f"  OCR 重试 {attempt + 1}, 等待 {wait_time}s...")
            time.sleep(wait_time)

    return f"[OCR失败: {last_error}]"


def format_to_markdown(ocr_text):
    """将 OCR 文字格式化为 Markdown"""
    url = "https://api.moonshot.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {KIMI_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = """你是一个文档格式化专家。将 OCR 识别出的原始文字整理成格式规范的 Markdown。

要求：
1. 保持原文内容不变，只修复明显的 OCR 错别字
2. 合理划分段落和章节，使用 Markdown 标题层级（# ## ###）
3. 保持原文的缩进、列表格式（如 a) b) c) 或 1) 2) 3)）
4. 不要添加任何解释或评论
5. 直接输出 Markdown 内容，不要代码块包裹"""

    payload = {
        "model": KIMI_TEXT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请格式化为 Markdown：\n\n{ocr_text}"}
        ],
        "max_tokens": 4096
    }

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            with httpx.Client(timeout=180) as client:
                response = client.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    content = content.strip()
                    if content.startswith("```"):
                        content = content[3:]
                    if content.endswith("```"):
                        content = content[:-3]
                    return content.strip()
                else:
                    last_error = f"错误 {response.status_code}: {response.text[:500]}"
        except Exception as e:
            last_error = str(e)

        if attempt < MAX_RETRIES - 1:
            wait_time = 2 ** attempt
            print(f"  格式化重试 {attempt + 1}, 等待 {wait_time}s...")
            time.sleep(wait_time)

    return f"[格式化失败: {last_error}]"


def summarize_page(content):
    """提取每个章节的要点"""
    url = "https://api.moonshot.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {KIMI_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = """你是一个文档总结专家。提取每个章节标题及其核心内容要点。

要求：
1. 只输出纯文本，每行一个章节
2. 格式：章节标题：要点（多个要点用分号分隔）
3. 例如：1 范围：本标准规定了军用软件开发文档编制的种类、结构、格式和内容等要求；本标准适用于军用软件开发过程中文档的编制
4. 不要任何列表符号（- *）、不要代码块
5. 保持原文措辞，只提取不修改"""

    payload = {
        "model": KIMI_TEXT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"提取章节要点（每行一个章节，纯文本格式）：\n\n{content}"}
        ],
        "max_tokens": 1024
    }

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            with httpx.Client(timeout=120) as client:
                response = client.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    content = content.strip()
                    if content.startswith("```"):
                        content = content[3:]
                    if content.endswith("```"):
                        content = content[:-3]
                    return content.strip()
                else:
                    last_error = f"错误 {response.status_code}: {response.text[:500]}"
        except Exception as e:
            last_error = str(e)

        if attempt < MAX_RETRIES - 1:
            wait_time = 2 ** attempt
            print(f"  总结重试 {attempt + 1}, 等待 {wait_time}s...")
            time.sleep(wait_time)

    return f"[总结失败: {last_error}]"


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not os.path.exists(TEST_PDF):
        print(f"文件不存在: {TEST_PDF}")
        return

    print(f"PDF: {TEST_PDF}")
    doc = fitz.open(TEST_PDF)
    total_pages = len(doc)
    doc.close()
    print(f"总页数: {total_pages}")

    all_ocr_results = []
    all_markdown_results = []
    all_summary_results = []

    # 逐页处理
    page_num = 1
    while page_num <= total_pages:
        print(f"\n{'='*50}")
        print(f"处理第 {page_num} 页...")
        print(f"{'='*50}")

        # Step 1: PDF 转图片
        img_path = pdf_to_image_pymupdf(TEST_PDF, page_num, OUTPUT_DIR)
        print(f"图片: {img_path}")

        # Step 2: OCR
        print("OCR 识别中...")
        ocr_result = ocr_image(img_path)
        all_ocr_results.append(f"=== 第 {page_num} 页 OCR ===\n{ocr_result}\n")
        print(f"OCR: {len(ocr_result)} 字符")

        # Step 3: 格式化 Markdown
        print("格式化 Markdown...")
        markdown_result = format_to_markdown(ocr_result)
        all_markdown_results.append(markdown_result)
        print(f"格式化: {len(markdown_result)} 字符")

        # Step 4: 章节要点总结
        print("提取章节要点...")
        summary_result = summarize_page(markdown_result)
        all_summary_results.append(summary_result)
        print(f"总结: {len(summary_result)} 字符")

        page_num += 1

    # 保存结果
    # OCR 原始结果
    with open(os.path.join(OUTPUT_DIR, "kimi_all_in_one_ocr.txt"), "w", encoding="utf-8") as f:
        f.write(f"PDF: {TEST_PDF}\n总页数: {total_pages}\n\n")
        f.write("\n".join(all_ocr_results))

    # Markdown
    with open(os.path.join(OUTPUT_DIR, "kimi_all_in_one_formatted.md"), "w", encoding="utf-8") as f:
        f.write("# GJB 438C—2021 军用软件开发文档通用要求\n\n---\n\n")
        f.write("\n\n---\n\n".join(all_markdown_results))
        f.write("\n")

    # 章节要点总结
    with open(os.path.join(OUTPUT_DIR, "kimi_all_in_one_summary.txt"), "w", encoding="utf-8") as f:
        f.write("GJB 438C—2021 军用软件开发文档通用要求\n")
        f.write("=" * 50 + "\n\n")
        for i, summary in enumerate(all_summary_results, 1):
            f.write(f"{i}. {summary}\n\n")

    print(f"\n完成！生成文件：")
    print(f"  - {OUTPUT_DIR}/kimi_all_in_one_ocr.txt")
    print(f"  - {OUTPUT_DIR}/kimi_all_in_one_formatted.md")
    print(f"  - {OUTPUT_DIR}/kimi_all_in_one_summary.txt")


if __name__ == "__main__":
    main()
