#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
对齐 resources/examples/game/werewolves/test_kimi.py：
用 ReActAgent + KimiHTTPChatModel 做一次最小对话测试。

用法（在 backend 目录）:
  set PYTHONPATH=.
  python test_react_doc_review.py

需要环境变量: KIMI_API_KEY；可选 AGENTSCOPE_STUDIO_URL。
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# 保证可导入 agents 包
_BACKEND_ROOT = Path(__file__).resolve().parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

load_dotenv(_BACKEND_ROOT / ".env")


async def main() -> None:
    key = os.environ.get("KIMI_API_KEY")
    if not key:
        print("SKIP: 未设置 KIMI_API_KEY")
        sys.exit(0)

    import agentscope
    from agentscope.message import Msg

    studio = (os.environ.get("AGENTSCOPE_STUDIO_URL") or "").strip().strip('"')
    if studio:
        agentscope.init(
            studio_url=studio,
            project="doc_revewer",
            name="react_doc_review_test",
        )
        agentscope._config.trace_enabled = True
    else:
        print("提示: 未设置 AGENTSCOPE_STUDIO_URL，仅验证 API 调用")

    from agents.agentscope_agent import create_document_review_react_agent, msg_to_text

    agent = create_document_review_react_agent(
        api_key=key,
        sys_prompt="你是一个有帮助的助手。",
        name="DocReviewerTest",
        max_iters=3,
    )
    out = await agent(Msg("user", "请用一句话介绍你自己。", "user"))
    text = msg_to_text(out)
    print("Reply:", text[:200] + ("..." if len(text) > 200 else ""))
    print("OK: ReActAgent + KimiHTTPChatModel 调用成功")


if __name__ == "__main__":
    asyncio.run(main())
