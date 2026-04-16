"""
调试脚本：验证 RuleClassifierAgent 对规则 content 的“总结化”效果。

运行：
    cd backend
    python test/debug_rule_classifier_output.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.rule_classifier_agent import RuleClassifierAgent


RAW_RULES_JSON = r"""
[
  {
    "title": "接口唯一标识符要求",
    "content": "本条（从4.3.2开始）应通过唯一标识符来标识接口，应简要地标识接口实体，根据需要可分条描述单方或双方接口实体的特性。",
    "rule_group": "接口设计"
  },
  {
    "title": "接口实体特性描述",
    "content": "如果一指定的接口实体包含在本SDD中（例如，一个外部系统），而描述接口实体需要提到其接口特性时，这些特性应作为假设予以陈述。或以“当[未涵盖的实体]这样做时，[所指定的实体]将……”的形式描述。",
    "rule_group": "接口设计"
  },
  {
    "title": "引用其他文档",
    "content": "本条可引用其他文档（例如数据字典、协议标准、用户接口标准）代替在此所描述的信息。",
    "rule_group": "接口设计"
  },
  {
    "title": "接口实体优先级",
    "content": "a) 接口实体分配给接口的优先级。",
    "rule_group": "数据元素"
  },
  {
    "title": "接口类型特征",
    "content": "b) 所实现的接口类型（如实时数据传送、数据的存储和检索等）的特征。",
    "rule_group": "数据元素"
  },
  {
    "title": "数据元素特征",
    "content": "c) 接口实体所提供、存储、发送、访问和接收的各个数据元素的特征，例如：1. 名称/标识符：a. 唯一标识符；b. 非技术名称（自然语言名称）；c. 数据元素名称（应优先使用标准化的数据元素名称）；d. 技术名称（如在代码或数据库中的变量名或字段名）；e. 缩略名或同义词。2. 数据类型（字母、数字、整数等）。3. 大小与格式（如：字符串的长度）。4. 计量单位（如：m等）。5. 可能值的范围或枚举（如：0~99）。6. 准确性（正确程度）和精度（有效数位数）。7. 优先级、定时、频率、容量、序列以及其他约束条件（例如数据元素是否可以被更新、业务规则是否适用）。8. 保密性约束。9. 来源（建立/发送实体）和接受者（使用/接收实体）。",
    "rule_group": "数据元素"
  },
  {
    "title": "数据元素组合体特征",
    "content": "d) 接口实体所提供、存储、发送、访问和接收的数据元素组合体（记录、消息、文件、数组、显示和报表等）的特征，例如：1. 名称/标识符：a. 唯一标识符；b. 非技术名称（自然语言名称）；c. 技术名称（如系统中变量名称、数据库字段名称）；d. 缩略名或同义词。2. 数据元素组合体中的数据元素及其结构（编号、顺序和分组情况）。3. 介质（例如光盘）以及介质上数据元素/数据组合体的结构。4. 显示和其他输出的视听特性（例如颜色、布局、字体、图标和其他显示元素、峰鸣声和亮度）。5. 数据组合体之间的关系，如排序/存取特性。6. 优先级、定时、频率、容量、序列及其他约束，例如数据组合体是否可被更新、业务规则是否适用。7. 保密性约束。8. 来源（建立/发送实体）和接受者（使用/接收实体）。",
    "rule_group": "数据元素"
  },
  {
    "title": "接口通信方法特征",
    "content": "e) 接口实体所使用的接口通信方法的特征。",
    "rule_group": "通信方法"
  }
]
"""


class DebugBackend:
    """调试用 backend：模拟 LLM 总结输出，避免真实调用。"""

    def call_llm(
        self,
        system: str,
        user: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        marker = "原始规则："
        idx = user.find(marker)
        source = user[idx + len(marker) :].split("原文摘录：", 1)[0].strip() if idx >= 0 else user
        source = source.replace("\n", " ")
        # 返回一条可执行检查句（模拟模型行为）
        return f"文档应完整描述该规则要求，且不得缺少关键字段与约束条件（摘要）: {source[:36]}"


def to_grouped_payload(raw_rules: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in raw_rules:
        grouped[item.get("rule_group", "其他")].append(
            {
                "title": item.get("title", ""),
                "content": item.get("content", ""),
                "source_page": None,
                "source_excerpt": item.get("content", ""),
            }
        )
    return {
        "rule_groups": [
            {
                "group_name": group_name,
                "description": f"{group_name}类规则",
                "rules": rules,
            }
            for group_name, rules in grouped.items()
        ],
        "summary": "debug input",
    }


def main() -> None:
    raw_rules = json.loads(RAW_RULES_JSON)
    payload = to_grouped_payload(raw_rules)
    agent = RuleClassifierAgent(DebugBackend())

    normalized = agent._normalize_result(payload)
    print("=== 规则总结调试输出 ===")
    for group in normalized.get("rule_groups", []):
        print(f"\n[组] {group.get('group_name')}")
        for idx, rule in enumerate(group.get("rules", []), start=1):
            content = str(rule.get("content", ""))
            excerpt = str(rule.get("source_excerpt", ""))
            changed = "Y" if content != excerpt else "N"
            print(f"{idx:02d}. {rule.get('title')}")
            print(f"    changed: {changed}")
            print(f"    summary: {content}")


if __name__ == "__main__":
    main()
