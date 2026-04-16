"""
Kimi 图片 OCR 测试脚本
使用 PyMuPDF 将 PDF 转为图片
"""
import base64
import os
import httpx
from PIL import Image

# 配置
KIMI_API_KEY = "sk-tukbjrbeaxDKcsTyDIhGPB7zbO08Nd0BeVgIdAGJtURs9FpG"
KIMI_MODEL = "moonshot-v1-8k-vision-preview"  # Kimi 视觉模型

# 测试文件
TEST_PDF = "/mnt/d/WSL/file/软件开发文档通用要求-测试版.pdf"
# 输出到 /home/figodxdp/tmp，使用类似 UUID 的格式
import uuid
OUTPUT_DIR = f"/home/figodxp/tmp/import_{uuid.uuid4().hex[:8]}"


def pdf_to_image_pymupdf(pdf_path, page_num, output_dir, dpi=150, min_size=400):
    """使用 PyMuPDF 将 PDF 转为图片"""
    import fitz

    doc = fitz.open(pdf_path)
    if page_num > len(doc):
        return None

    page = doc[page_num - 1]
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)

    img_path = os.path.join(output_dir, f"kimi_page_{page_num}.png")
    pix.save(img_path)

    with Image.open(img_path) as img:
        # 短边至少要满足要求
        width, height = img.size
        if width < min_size and height < min_size:
            scale = min_size / min(width, height)
            new_size = (int(width * scale), int(height * scale))
            img = img.resize(new_size, Image.LANCZOS)
        # 转为 JPEG 压缩
        import io
        buffer = io.BytesIO()
        img = img.convert('RGB')
        img.save(buffer, format='JPEG', quality=90, optimize=True)
        buffer.seek(0)
        with open(img_path.replace('.png', '.jpg'), 'wb') as f:
            f.write(buffer.read())
        img_path = img_path.replace('.png', '.jpg')

    return img_path


def encode_image(image_path):
    """图片转 base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_image_size(image_path):
    return os.path.getsize(image_path) / 1024


def test_kimi_ocr(image_path):
    """Kimi OCR"""
    if not KIMI_API_KEY:
        return "错误: 未设置 KIMI_API_KEY"

    base64_img = encode_image(image_path)
    img_size = get_image_size(image_path)

    print(f"  图片大小: {img_size:.1f} KB")
    print(f"  Base64长度: {len(base64_img)} 字符")

    url = "https://api.moonshot.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {KIMI_API_KEY}",
        "Content-Type": "application/json"
    }

    # Kimi 视觉模型使用 OpenAI 兼容格式
    payload = {
        "model": KIMI_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "这是一张PDF截图，请识别其中的文字内容，直接输出文字，不要其他说明。"
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

    try:
        with httpx.Client(timeout=180) as client:
            response = client.post(url, headers=headers, json=payload)
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.text[:2000]}")
            if response.status_code == 200:
                result = response.json()
                print(f"JSON: {result}")
                return result["choices"][0]["message"]["content"]
            else:
                return f"错误 {response.status_code}: {response.text[:500]}"
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"异常: {str(e)}"


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not KIMI_API_KEY:
        print("请设置 KIMI_API_KEY")
        return

    if not os.path.exists(TEST_PDF):
        print(f"文件不存在: {TEST_PDF}")
        return

    print(f"PDF: {TEST_PDF}")

    import fitz
    doc = fitz.open(TEST_PDF)
    total_pages = len(doc)
    doc.close()
    print(f"总页数: {total_pages}")

    page_num = 1
    all_results = []

    # 循环处理所有页面
    while page_num <= total_pages:
        print(f"\n处理第 {page_num} 页...")

        img_path = pdf_to_image_pymupdf(TEST_PDF, page_num, OUTPUT_DIR)
        print(f"图片: {img_path}")

        result = test_kimi_ocr(img_path)
        all_results.append(f"=== 第 {page_num} 页 ===\n{result}\n")

        page_num += 1

    # 合并所有结果
    result = "\n".join(all_results)

    print(f"\n结果:\n{result[:1500]}...")

    output_file = os.path.join(OUTPUT_DIR, "kimi_pymupdf_result.txt")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"PDF: {TEST_PDF}\n")
        f.write(f"页码: {page_num}\n")
        f.write(f"图片: {img_path}\n")
        f.write(f"\n结果:\n{result}\n")

    print(f"\n结果已保存到: {output_file}")


if __name__ == "__main__":
    main()
