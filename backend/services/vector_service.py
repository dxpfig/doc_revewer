"""
Vector Service - 向量存储服务
使用简单文本匹配作为后备，也可以集成向量数据库
"""
import logging
import re
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class VectorService:
    """Service for text similarity and vector operations"""

    def __init__(self):
        self._indexed_documents: Dict[str, Dict[str, Any]] = {}

    def index_document(
        self,
        doc_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """索引文档"""
        self._indexed_documents[doc_id] = {
            "content": content,
            "metadata": metadata or {},
            "tokens": self._tokenize(content)
        }

    def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.1
    ) -> List[Dict[str, Any]]:
        """
        搜索相关文档

        Args:
            query: 查询文本
            top_k: 返回前 k 个结果
            threshold: 相似度阈值

        Returns:
            搜索结果列表
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        results = []
        for doc_id, doc in self._indexed_documents.items():
            score = self._calculate_similarity(query_tokens, doc["tokens"])
            if score >= threshold:
                results.append({
                    "doc_id": doc_id,
                    "score": score,
                    "content": doc["content"][:500],  # 截取部分内容
                    "metadata": doc["metadata"]
                })

        # 按分数排序
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _tokenize(self, text: str) -> List[str]:
        """简单分词"""
        # 转为小写，提取中文和英文单词
        text = text.lower()
        tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', text)
        # 过滤停用词和过短的词
        stopwords = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这'}
        return [t for t in tokens if t not in stopwords and len(t) > 1]

    def _calculate_similarity(
        self,
        query_tokens: List[str],
        doc_tokens: List[str]
    ) -> float:
        """计算简单相似度（基于 token 重叠）"""
        if not query_tokens or not doc_tokens:
            return 0.0

        # 使用 Jaccard 相似度
        query_set = set(query_tokens)
        doc_set = set(doc_tokens)

        intersection = len(query_set & doc_set)
        union = len(query_set | doc_set)

        return intersection / union if union > 0 else 0.0

    def find_rule_matches(
        self,
        content: str,
        rules: List[Dict[str, Any]],
        threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        在文档中查找匹配的规则

        Args:
            content: 文档内容
            rules: 规则列表
            threshold: 匹配阈值

        Returns:
            匹配结果列表
        """
        content_tokens = self._tokenize(content)
        matches = []

        for rule in rules:
            rule_title_tokens = self._tokenize(rule.get("title", ""))
            rule_content_tokens = self._tokenize(rule.get("content", ""))

            # 计算两个相似度
            title_sim = self._calculate_similarity(content_tokens, rule_title_tokens)
            content_sim = self._calculate_similarity(content_tokens, rule_content_tokens)

            best_score = max(title_sim, content_sim)

            if best_score >= threshold:
                matches.append({
                    "rule_id": rule.get("id"),
                    "rule_title": rule.get("title"),
                    "match_score": best_score,
                    "matched": True
                })
            else:
                matches.append({
                    "rule_id": rule.get("id"),
                    "rule_title": rule.get("title"),
                    "match_score": best_score,
                    "matched": False
                })

        # 按分数排序
        matches.sort(key=lambda x: x["match_score"], reverse=True)
        return matches

    def clear_index(self):
        """清空索引"""
        self._indexed_documents.clear()

    def get_index_stats(self) -> Dict[str, Any]:
        """获取索引统计"""
        return {
            "total_documents": len(self._indexed_documents),
            "documents": list(self._indexed_documents.keys())
        }


# 全局向量服务实例
_global_vector_service: Optional[VectorService] = None


def get_vector_service() -> VectorService:
    """获取全局向量服务实例"""
    global _global_vector_service
    if _global_vector_service is None:
        _global_vector_service = VectorService()
    return _global_vector_service


def reset_vector_service():
    """重置全局向量服务"""
    global _global_vector_service
    if _global_vector_service:
        _global_vector_service.clear_index()
    _global_vector_service = None