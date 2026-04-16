"""
规则提取脚本 - 将GJB文档内容提炼为结构化规则条目
用于录入数据库和页面的规则数据
"""
import os
import json
import httpx
import time

# 配置
KIMI_API_KEY = "sk-tukbjrbeaxDKcsTyDIhGPB7zbO08Nd0BeVgIdAGJtURs9FpG"
KIMI_TEXT_MODEL = "moonshot-v1-8k"  # Kimi 文本模型
MAX_RETRIES = 5

# 输出目录 - parser_stander
OUTPUT_DIR = "/home/figodxp/tmp/parser_stander"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "规则提取结果.json")


def extract_rules_from_text(text, page_num=4):
    """使用LLM从文本中提取结构化规则条目"""

    url = "https://api.moonshot.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {KIMI_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = """你是一个专业的文档规则提取专家。从GJB标准的正文中提取可以作为规则条目录入数据库的结构化数据。

提取要求：
1. 每条规则应该包含以下字段：
   - title: 规则标题（简洁明确，50字以内）
   - content: 规则详细内容（完整保留原文的要点）
   - rule_group: 规则所属分组（根据内容归类，如"接口设计"、"数据元素"、"通信方法"等）

2. 提取规则：
   - 只提取具有明确要求的条款（包含"应"、"必须"、"应该"等指令性词汇的内容）
   - 保持原文的层次结构（a) b) c) 或 1) 2) 3) 格式）
   - 如果一个条款下有多个子项，可以拆分为多条规则
   - 每条规则要完整表达一个独立的要求

3. 输出格式：
   - 输出JSON数组，每个元素是一个规则对象
   - 直接输出JSON，不要代码块包裹
   - 不要添加任何解释或评论

示例输出：
[
  {"title": "接口唯一标识符要求", "content": "本条（从4.3.2开始）应通过唯一标识符来标识接口，应简要地标识接口实体", "rule_group": "接口设计"},
  {"title": "接口实体特性描述", "content": "根据需要可分条描述单方或双方接口实体的特性", "rule_group": "接口设计"}
]"""

    payload = {
        "model": KIMI_TEXT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请从以下第{page_num}页内容中提取规则条目：\n\n{text}"}
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
                    # 清理输出
                    content = content.strip()
                    if content.startswith("```"):
                        content = content[3:]
                    if content.endswith("```"):
                        content = content[:-3]
                    return json.loads(content.strip())
                else:
                    last_error = f"错误 {response.status_code}: {response.text[:500]}"
        except json.JSONDecodeError as e:
            # 如果JSON解析失败，尝试提取代码块中的内容
            try:
                start = content.find('[')
                end = content.rfind(']') + 1
                if start >= 0 and end > start:
                    return json.loads(content[start:end])
            except:
                pass
            last_error = f"JSON解析失败: {str(e)}"
        except Exception as e:
            last_error = str(e)

        if attempt < MAX_RETRIES - 1:
            wait_time = 2 ** attempt
            print(f"  重试 {attempt + 1}, 等待 {wait_time}s...")
            time.sleep(wait_time)

    print(f"[提取失败: {last_error}]")
    return []


def main():
    print("=" * 60)
    print("GJB 438C-2021 规则提取工具")
    print("=" * 60)

    # 检查输入目录
    if not os.path.exists(INPUT_DIR):
        print(f"输入目录不存在: {INPUT_DIR}")
        return

    # 获取所有OCR文件
    ocr_files = sorted([f for f in os.listdir(INPUT_DIR) if f.endswith('_ocr.txt')])
    print(f"找到 {len(ocr_files)} 个OCR文件")

    all_rules = []

    # 处理每个文件
    for ocr_file in ocr_files:
        # 从文件名提取页码
        page_num = int(ocr_file.split('_')[1]) if '_' in ocr_file else 0

        file_path = os.path.join(INPUT_DIR, ocr_file)
        print(f"\n处理: {ocr_file} (页码: {page_num})")

        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()

        # 跳过markdown标记行
        if text.strip().startswith('markdown'):
            text = text.replace('markdown\n', '', 1)

        print(f"  文本长度: {len(text)} 字符")

        # 提取规则
        rules = extract_rules_from_text(text, page_num)
        print(f"  提取到 {len(rules)} 条规则")

        # 添加页码信息
        for rule in rules:
            rule['source_page'] = page_num

        all_rules.extend(rules)

    # 保存结果
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_rules, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"完成！共提取 {len(all_rules)} 条规则")
    print(f"结果保存至: {OUTPUT_FILE}")
    print(f"{'=' * 60}")

    # 打印规则预览
    print("\n规则预览（前5条）:")
    for i, rule in enumerate(all_rules[:5], 1):
        print(f"\n{i}. {rule.get('title', '无标题')}")
        print(f"   分组: {rule.get('rule_group', '未分组')}")
        print(f"   内容: {rule.get('content', '')[:100]}...")


if __name__ == "__main__":
    main()