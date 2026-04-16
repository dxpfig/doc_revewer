"""
Kimi Markdown 内容总结脚本
将格式化的 Markdown 文件按页总结成列表
"""
import os
import httpx
import time

# 配置
KIMI_API_KEY = "sk-tukbjrbeaxDKcsTyDIhGPB7zbO08Nd0BeVgIdAGJtURs9FpG"
KIMI_TEXT_MODEL = "moonshot-v1-8k"  # Kimi 文本模型

# 输入输出文件
# 使用 /home/figodxp/tmp，参考 import_68e2b976 格式
INPUT_MD = "/home/figodxp/tmp/import_68e2b976/kimi_ocr_formatted.md"
OUTPUT_FILE = "/home/figodxp/tmp/import_68e2b976/kimi_ocr_summary.txt"
MAX_RETRIES = 5


def summarize_page(content, page_num):
    """使用 Kimi 总结单页内容"""
    url = "https://api.moonshot.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {KIMI_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = """你是一个文档总结专家。你的任务是提取文档某一页中每个章节标题及其包含的具体内容要点。

要求：
1. 列出这一页中包含的主要章节标题（如 "1 范围"、"3.1 术语和定义"）
2. 对每个章节，用原文中的原话概括其核心内容，不要自己总结
3. 格式：章节标题：内容要点（用分号分隔多个要点）
4. 必须保持原文的措辞，只提取不修改
5. 只输出总结内容，不要任何前缀说明
6. 如果某个章节内容较多，可以提取最核心的2-3条要点"""

    user_prompt = f"""这是文档第 {page_num} 页的内容，请按以下格式提取：
章节标题：内容要点1；内容要点2

例如：
需求可追踪性：从本文档所标识的每个软件单元，到分配给它的CSCI需求的可追踪性；从每个CSCI需求，到被分配这些需求的软件单元的可追踪性

请提取所有章节的内容要点：

```
{content}
```"""

    payload = {
        "model": KIMI_TEXT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
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
                    # 清理可能的引号和标记
                    content = content.strip().strip('"').strip("'").strip()
                    # 去掉可能的 markdown 标记
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

    return f"[总结失败: {last_error}]"


def main():
    if not os.path.exists(INPUT_MD):
        print(f"文件不存在: {INPUT_MD}")
        return

    # 读取 Markdown 文件
    with open(INPUT_MD, "r", encoding="utf-8") as f:
        content = f.read()

    # 去掉标题部分（第一行 # 开头到第一个 ---）
    lines = content.split("\n")
    start_idx = 0
    for i, line in enumerate(lines):
        if line.strip() == "---":
            start_idx = i + 1
            break

    # 剩余内容按 --- 分隔成多页
    remaining = "\n".join(lines[start_idx:])
    pages = remaining.split("\n---\n")

    print(f"共找到 {len(pages)} 页内容")

    summaries = []
    for i, page in enumerate(pages):
        page_num = i + 1
        if not page.strip():
            summaries.append(f"[第 {page_num} 页: 空内容]")
            continue

        print(f"\n总结第 {page_num} 页...")
        summary = summarize_page(page.strip(), page_num)
        summaries.append(f"{page_num}. {summary}")
        print(f"  总结: {summary}")

    # 保存结果
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("GJB 438C—2021 军用软件开发文档通用要求\n")
        f.write("=" * 50 + "\n\n")
        for item in summaries:
            f.write(item + "\n")

    print(f"\n总结完成，已保存到: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
