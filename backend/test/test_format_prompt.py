"""测试新的 FormatMarkdownSkill prompt"""
import os
import sys

# 添加parent path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv

# 加载 .env
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

from agents.skills.pdf_skills import FormatMarkdownSkill

KIMI_API_KEY = os.getenv("KIMI_API_KEY", "sk-tukbjrbeaxDKcsTyDIhGPB7zbO08Nd0BeVgIdAGJtURs9FpG")
KIMI_TEXT_MODEL = os.getenv("KIMI_TEXT_MODEL", "moonshot-v1-8k")

test_text = """c) 接口实体所提供、存储、发送、访问和接收的各个数据元素的特征，例如：1. 名称/标识符：a. 唯一标识符；b. 非技术名称（自然语言名称）；c. 数据元素名称（应优先使用标准化的数据元素名称）；d. 技术名称（如在代码或数据库中的变量名或字段名）；e. 缩略名或同义词。2. 数据类型（字母、数字、整数等）。3. 大小与格式（如：字符串的长度）。4. 计量单位（如：m等）。5. 可能值的范围或枚举（如：0~99）。6. 准确性（正确程度）和精度（有效数位数）。7. 优先级、定时、频率、容量、序列以及其他约束条件（例如数据元素是否可以被更新、业务规则是否适用）。8. 保密性约束。9. 来源（建立/发送实体）和接受者（使用/接收实体）。"""

print("=" * 60)
print("输入文本:")
print("=" * 60)
print(test_text)
print("\n" + "=" * 60)
print("调用 FormatMarkdownSkill...")
print("=" * 60)

skill = FormatMarkdownSkill(api_key=KIMI_API_KEY, text_model=KIMI_TEXT_MODEL)
result = skill.run(test_text)

if result.get("ok"):
    print("\n" + "=" * 60)
    print("输出结果:")
    print("=" * 60)
    print(result["text"])
else:
    print(f"\n错误: {result.get('error')}")