#!/bin/bash
# T3 真实测试运行脚本
# 使用: bash tests/real/run_all.sh
# 前置条件: .env 和 configs/email.yaml 已配置

set -e
cd "$(dirname "$0")/../.."

echo "=== T3 Real Integration Tests ==="
echo ""

echo "--- CrossRef API ---"
python tests/real/real_crossref.py
echo ""

echo "--- DeepSeek LLM API ---"
python tests/real/real_llm_api.py
echo ""

echo "--- Email SMTP ---"
python tests/real/real_email.py
echo ""

echo "=== All T3 tests completed ==="
