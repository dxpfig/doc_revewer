"""
Kimi OCR + 格式化测试脚本
PDF -> 图片 -> OCR 识别 -> 大模型格式化 -> Markdown 文件
"""
import base64
import os
import httpx
from PIL import Image
import fitz
import time

# 配置
KIMI_API_KEY = "sk-tukbjrbeaxDKcsTyDIhGPB7zbO08Nd0BeVgIdAGJtURs9FpG"
KIMI_MODEL = "moonshot-v1-8k-vision-preview"  # Kimi 视觉模型（OCR）
KIMI_TEXT_MODEL = "moonshot-v1-8k"  # Kimi 文本模型（格式化）

# 测试文件
TEST_PDF = "/mnt/d/WSL/file/软件开发文档通用要求-测试版.pdf"
# 输出到 /home/figodxp/tmp，使用类似 UUID 的格式
import uuid
OUTPUT_DIR = f"/home/figodxp/tmp/import_{uuid.uuid4().hex[:8]}"
MAX_RETRIES = 3


def pdf_to_image_pymupdf(pdf_path, page_num, output_dir, dpi=150, min_size=400):
    """使用 PyMuPDF 将 PDF 转为 JPEG 图片"""
    doc = fitz.open(pdf_path)
    if page_num > len(doc):
        return None

    page = doc[page_num - 1]
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)

    # 先生成临时 PNG
    temp_png = os.path.join(output_dir, f"temp_page_{page_num}.png")
    pix.save(temp_png)

    # 转换为 JPEG
    img_path = os.path.join(output_dir, f"kimi_ocr_page_{page_num}.jpg")
    with Image.open(temp_png) as img:
        width, height = img.size
        if width < min_size and height < min_size:
            scale = min_size / min(width, height)
            new_size = (int(width * scale), int(height * scale))
            img = img.resize(new_size, Image.LANCZOS)
        img = img.convert('RGB')
        img.save(img_path, format='JPEG', quality=90, optimize=True)

    # 删除临时 PNG
    os.remove(temp_png)
    doc.close()
    return img_path


def encode_image(image_path):
    """图片转 base64"""
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
        "model": KIMI_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "请识别图片中的所有文字内容，直接输出文字，不要其他说明。"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_img}"
                        }
                    }
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
                    print(f"  第 {attempt + 1} 次尝试失败: {last_error}")
        except Exception as e:
            last_error = str(e)
            print(f"  第 {attempt + 1} 次尝试异常: {last_error}")

        if attempt < MAX_RETRIES - 1:
            wait_time = 2 ** attempt  # 指数退避: 1s, 2s, 4s
            print(f"  等待 {wait_time} 秒后重试...")
            time.sleep(wait_time)

    return f"重试 {MAX_RETRIES} 次后失败: {last_error}"


def format_to_markdown(ocr_text, page_num):
    """使用大模型将 OCR 文字格式化为 Markdown，带重试机制"""
    url = "https://api.moonshot.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {KIMI_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = """你是一个文档格式化专家。你的任务是将 OCR 识别出来的原始文字整理成格式规范的 Markdown 文档。

要求：
1. 保持原文内容不变，只修复因 OCR 识别错误导致的明显错别字
2. 合理划分段落和章节，使用 Markdown 标题层级（# ## ###）
3. 保持原文的缩进、列表格式（如 a) b) c) 或 1) 2) 3)）
4. 保持表格格式（如果原文有表格）
5. 不要添加任何你自己的解释或评论
6. 直接输出 Markdown 内容，不要使用代码块包裹
7. 如果发现内容不完整（因为是 PDF 某一页的内容），保持原样即可"""

    user_prompt = f"""这是第 {page_num} 页的 OCR 识别结果，请将其格式化为规范的 Markdown（直接输出，不要代码块）：

```
{ocr_text}
```"""

    payload = {
        "model": KIMI_TEXT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
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
                    # 去掉可能出现的代码块标记
                    content = content.strip()
                    if content.startswith("```markdown"):
                        content = content[11:]
                    if content.startswith("```"):
                        content = content[3:]
                    if content.endswith("```"):
                        content = content[:-3]
                    return content.strip()
                else:
                    last_error = f"错误 {response.status_code}: {response.text[:500]}"
                    print(f"  第 {attempt + 1} 次尝试失败: {last_error}")
        except Exception as e:
            last_error = str(e)
            print(f"  第 {attempt + 1} 次尝试异常: {last_error}")

        if attempt < MAX_RETRIES - 1:
            wait_time = 2 ** attempt
            print(f"  等待 {wait_time} 秒后重试...")
            time.sleep(wait_time)

    return f"重试 {MAX_RETRIES} 次后失败: {last_error}"


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not KIMI_API_KEY:
        print("请设置 KIMI_API_KEY")
        return

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

    # 逐页处理
    page_num = 1
    while page_num <= total_pages:
        print(f"\n{'='*50}")
        print(f"处理第 {page_num} 页...")
        print(f"{'='*50}")

        # Step 1: PDF 转图片
        img_path = pdf_to_image_pymupdf(TEST_PDF, page_num, OUTPUT_DIR)
        print(f"图片: {img_path}")

        # Step 2: OCR 识别
        print("正在 OCR 识别...")
        ocr_result = ocr_image(img_path)
        all_ocr_results.append(f"=== 第 {page_num} 页 OCR 结果 ===\n{ocr_result}\n")
        print(f"OCR 完成: {len(ocr_result)} 字符")

        # Step 3: 格式化 Markdown
        print("正在格式化 Markdown...")
        markdown_result = format_to_markdown(ocr_result, page_num)
        all_markdown_results.append(markdown_result)
        print(f"格式化完成: {len(markdown_result)} 字符")

        page_num += 1

    # 保存 OCR 原始结果
    ocr_output = os.path.join(OUTPUT_DIR, "kimi_ocr_raw.txt")
    with open(ocr_output, "w", encoding="utf-8") as f:
        f.write(f"PDF: {TEST_PDF}\n")
        f.write(f"总页数: {total_pages}\n")
        f.write("\n".join(all_ocr_results))
    print(f"\nOCR 原始结果已保存: {ocr_output}")

    # 保存格式化后的 Markdown
    md_output = os.path.join(OUTPUT_DIR, "kimi_ocr_formatted.md")
    with open(md_output, "w", encoding="utf-8") as f:
        # 添加标题
        f.write("# GJB 438C—2021 军用软件开发文档通用要求\n\n")
        f.write("---\n\n")
        # 合并所有 Markdown
        f.write("\n\n---\n\n".join(all_markdown_results))
        f.write("\n")  # 确保文件有换行结尾
    print(f"Markdown 已保存: {md_output}")

    print(f"\n完成！")


if __name__ == "__main__":
    main()
