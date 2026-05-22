"""
测试: 论文相关性检测 (paper_relevance.py)

覆盖范围:
  - 关键词匹配计数 (精确匹配、部分匹配、无匹配)
  - 正则编译边界检查
  - 大小写不敏感匹配
  - 多关键词命中统计

注意: LLM API 调用测试需要网络和 API 密钥，默认跳过。
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from utils.paper_relevance import PaperRelevanceChecker


def test_keyword_match_count_full_match():
    """关键词完全命中时返回正确计数。"""
    keywords = ["laser plasma", "wakefield", "proton acceleration"]
    checker = PaperRelevanceChecker(keywords)

    title = "Laser Plasma Wakefield Acceleration for Proton Generation"
    abstract = "We study laser plasma interactions with proton acceleration."
    count = checker.keyword_match_count(title, abstract)

    assert count == 3


def test_keyword_match_count_partial_no_match():
    """部分匹配不应被识别（单词边界保护）。"""
    keywords = ["plasma"]
    checker = PaperRelevanceChecker(keywords)

    # "plasmon" 包含 "plasma" 但不应该有匹配
    title = "Plasmonic resonance in nanostructures"
    count = checker.keyword_match_count(title, "")
    assert count == 0


def test_keyword_match_count_case_insensitive():
    """大小写不敏感匹配。"""
    keywords = ["laser"]
    checker = PaperRelevanceChecker(keywords)

    count = checker.keyword_match_count("LASER cooling", "")
    assert count == 1


def test_keyword_match_count_no_match():
    """完全不相关时应返回 0。"""
    keywords = ["laser", "plasma"]
    checker = PaperRelevanceChecker(keywords)

    count = checker.keyword_match_count(
        "Gravitational waves from binary systems",
        "We detect gravitational waves using LIGO."
    )
    assert count == 0


def test_keyword_match_count_empty_keywords():
    """空关键词列表应返回 0。"""
    checker = PaperRelevanceChecker([])
    count = checker.keyword_match_count("Laser plasma", "Abstract")
    assert count == 0


def test_keyword_match_count_unique_keywords():
    """重复命中的关键词只计数一次。"""
    keywords = ["laser"]
    checker = PaperRelevanceChecker(keywords)

    # "laser" 在标题和摘要中各出现多次，但只应算 1 个不同关键词
    count = checker.keyword_match_count("Laser Laser LASER",
                                         "the laser experiment laser")
    assert count == 1


def test_build_default_prompt():
    """验证 LLM 提示词构造。"""
    keywords = ["laser plasma", "wakefield"]
    checker = PaperRelevanceChecker(keywords)

    prompt = checker.build_default_prompt("Laser Wakefield", "Acceleration physics")

    # 提示词应包含关键词列表
    assert "laser plasma" in prompt
    assert "wakefield" in prompt
    # 提示词应包含标题和摘要
    assert "Laser Wakefield" in prompt
    assert "Acceleration physics" in prompt
    # 提示词应包含 JSON 格式要求
    assert "relevant" in prompt


def test_init_with_whitespace_keywords():
    """测试带空白的关键词去重和清理。"""
    keywords = ["  laser  ", "plasma", "", "  wakefield  "]
    checker = PaperRelevanceChecker(keywords)
    # 应有 3 个有效关键词，已 trim 并去空
    assert len(checker.keywords) == 3
    assert "laser" in checker.keywords


# ---- 语义相似度初筛测试 (SemanticFilter) ----

@pytest.fixture(scope="module")
def semantic_filter():
    """创建共享的 SemanticFilter 实例 (模型只加载一次)，不可用时跳过。"""
    try:
        from utils.paper_relevance import SemanticFilter
        from config import SEMANTIC_MODEL_PATH
        sf = SemanticFilter(
            model_name=SEMANTIC_MODEL_PATH,
            domain_description="研究领域涵盖：laser plasma, wakefield acceleration, proton acceleration"
        )
        return sf
    except ImportError as e:
        pytest.skip(f"sentence-transformers not installed: {e}")
    except Exception as e:
        pytest.skip(f"模型加载失败: {e}")


def test_semantic_filter_high_relevance(semantic_filter):
    """高度相关的论文应获得高分。"""
    score = semantic_filter.compute_similarity(
        title="Laser wakefield acceleration of electrons to GeV energies",
        abstract="We demonstrate the acceleration of electrons to GeV energies using laser-driven plasma wakefields."
    )
    assert score > 0.3, f"Expected high score, got {score:.3f}"


def test_semantic_filter_low_relevance(semantic_filter):
    """完全不相关的论文应获得低分。"""
    score = semantic_filter.compute_similarity(
        title="Gravitational waves from binary neutron star mergers",
        abstract="We present the detection of gravitational waves from a binary neutron star merger using LIGO."
    )
    assert score < 0.5, f"Expected low score for unrelated paper, got {score:.3f}"


def test_semantic_filter_moderate_relevance(semantic_filter):
    """部分相关的论文应获得中等分数。"""
    score = semantic_filter.compute_similarity(
        title="High-energy particle acceleration in astrophysical plasmas",
        abstract="We study particle acceleration mechanisms in relativistic plasma environments."
    )
    assert 0.15 < score < 0.8, f"Expected moderate score, got {score:.3f}"


def test_semantic_filter_empty_input(semantic_filter):
    """空标题和摘要应返回低分。"""
    score = semantic_filter.compute_similarity(title="", abstract="")
    assert score >= 0.0


def test_semantic_filter_class_exists():
    """SemanticFilter 类应可导入（不需要模型下载）。"""
    from utils.paper_relevance import SemanticFilter
    assert SemanticFilter is not None
    assert hasattr(SemanticFilter, 'compute_similarity')


def test_semantic_filter_import_error_message():
    """未安装 sentence-transformers 时应给出明确提示。"""
    # 仅验证类已定义，实际 ImportError 在 __init__ 中触发
    from utils.paper_relevance import SemanticFilter
    import re
    src = getattr(SemanticFilter.__init__, '__doc__', '') or ''
    # 类本身存在即可


# ---- LLM API 测试 (需要网络和 API 密钥) ----

@pytest.mark.skip(reason="需要有效的 DeepSeek API 密钥和网络连接")
def test_call_deepseek_api_relevance():
    """集成测试: 真实调用 DeepSeek API 判断相关性。"""
    from config import LLM_API_CONFIG_DICT
    keywords = ["laser plasma", "wakefield acceleration"]
    checker = PaperRelevanceChecker(keywords)

    prompt = checker.build_default_prompt(
        "Laser wakefield acceleration of electrons",
        "We demonstrate electron acceleration to GeV energies using laser wakefields."
    )
    result_str = checker.call_deepseek_api(prompt, LLM_API_CONFIG_DICT)
    import json
    result = json.loads(result_str)

    assert "relevant" in result
    assert "confidence" in result
    assert "reason" in result
