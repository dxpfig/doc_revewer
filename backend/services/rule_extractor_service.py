"""
Rule Extractor Service - 规则提取服务
封装规则提取功能，提供 CLI 和 API 接口
"""
import os
import json
import logging
import time
from typing import List, Dict, Any, Optional
from pathlib import Path

from config import KIMI_API_KEY, KIMI_TEXT_MODEL
from agents.rule_extractor_agent import RuleExtractorAgent, create_rule_extractor

logger = logging.getLogger(__name__)


class RuleExtractorService:
    """Service for extracting rules from documents"""

    def __init__(
        self,
        provider_type: str = "moonshot",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        """初始化规则提取服务

        Args:
            provider_type: LLM provider 类型
            api_key: API 密钥
            base_url: API 基础 URL
            model: 模型名称
        """
        # 创建规则提取 Agent（使用 factory 函数避免抽象类实例化问题）
        self.extractor = create_rule_extractor(
            provider_type=provider_type,
            api_key=api_key or KIMI_API_KEY,
            base_url=base_url or "https://api.moonshot.cn/v1",
            model=model or KIMI_TEXT_MODEL
        )

    def extract_from_directory(
        self,
        input_dir: str,
        output_dir: Optional[str] = None,
        max_retries: int = 3
    ) -> List[Dict[str, Any]]:
        """
        从目录中的 OCR 文件提取规则

        Args:
            input_dir: OCR 文件所在目录
            output_dir: 输出目录（默认与输入目录相同）
            max_retries: 最大重试次数

        Returns:
            提取的规则列表
        """
        if not os.path.exists(input_dir):
            raise ValueError(f"输入目录不存在: {input_dir}")

        # 默认输出到输入目录
        if output_dir is None:
            output_dir = input_dir

        # 获取所有 OCR 文件
        ocr_files = sorted([
            f for f in os.listdir(input_dir)
            if f.endswith('_ocr.txt')
        ])

        if not ocr_files:
            logger.warning(f"目录 {input_dir} 中没有找到 OCR 文件")
            return []

        logger.info(f"找到 {len(ocr_files)} 个 OCR 文件")

        all_rules = []

        for ocr_file in ocr_files:
            file_path = os.path.join(input_dir, ocr_file)

            # 从文件名提取页码
            page_num = self._extract_page_num(ocr_file)

            logger.info(f"处理: {ocr_file} (页码: {page_num})")

            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()

            # 提取规则
            rules = self.extractor.run(text, page_num, max_retries)
            logger.info(f"提取到 {len(rules)} 条规则")

            all_rules.extend(rules)

        # 保存结果到输出目录（与 OCR 文件同一位置）
        os.makedirs(output_dir, exist_ok=True)

        # 1. 保存提取的规则
        output_file = os.path.join(output_dir, "extracted_rules.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_rules, f, ensure_ascii=False, indent=2)
        logger.info(f"规则已保存至: {output_file}")

        # 2. 保存完整结果（包含提取过程信息）
        full_result = {
            "input_dir": input_dir,
            "total_pages": len(ocr_files),
            "total_rules": len(all_rules),
            "extracted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "rules": all_rules
        }
        output_full = os.path.join(output_dir, "extraction_result.json")
        with open(output_full, 'w', encoding='utf-8') as f:
            json.dump(full_result, f, ensure_ascii=False, indent=2)
        logger.info(f"完整结果已保存至: {output_full}")

        return all_rules

    def extract_from_text(
        self,
        text: str,
        page_num: Optional[int] = None,
        max_retries: int = 3
    ) -> List[Dict[str, Any]]:
        """
        从文本内容提取规则

        Args:
            text: 文档文本
            page_num: 页码
            max_retries: 最大重试次数

        Returns:
            规则列表
        """
        return self.extractor.run(text, page_num, max_retries)

    def _extract_page_num(self, filename: str) -> Optional[int]:
        """从文件名提取页码"""
        parts = filename.split('_')
        for i, part in enumerate(parts):
            if part == 'page' and i + 1 < len(parts):
                try:
                    return int(parts[i + 1].split('.')[0])
                except ValueError:
                    pass
        return None


def create_extractor_service(
    provider_type: str = "moonshot",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None
) -> RuleExtractorService:
    """创建规则提取服务的便捷函数"""
    return RuleExtractorService(
        provider_type=provider_type,
        api_key=api_key,
        base_url=base_url,
        model=model
    )


# CLI 入口
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="规则提取工具")
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="OCR 文件所在目录"
    )
    parser.add_argument(
        "--output", "-o",
        help="输出 JSON 文件路径"
    )
    parser.add_argument(
        "--provider",
        default="moonshot",
        help="LLM provider 类型"
    )
    parser.add_argument(
        "--api-key",
        help="API 密钥（可选，默认使用环境变量）"
    )
    parser.add_argument(
        "--model",
        help="模型名称（可选）"
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="最大重试次数"
    )

    args = parser.parse_args()

    # 创建服务
    service = create_extractor_service(
        provider_type=args.provider,
        api_key=args.api_key,
        model=args.model
    )

    # 提取规则
    print(f"开始从 {args.input} 提取规则...")
    rules = service.extract_from_directory(
        input_dir=args.input,
        output_file=args.output,
        max_retries=args.retries
    )

    print(f"\n完成！共提取 {len(rules)} 条规则")