"""
十一维量化交易系统 - 启动脚本

用法：
    # 每日策略（收盘后运行）
    python run_quant.py --mode daily

    # 单票评分
    python run_quant.py --mode score --codes 603290 688017

    # 回测
    python run_quant.py --mode backtest --start 2024-01-01 --end 2024-12-31

    # 盘中监控
    python run_quant.py --mode realtime
"""

import sys
import os

# 确保 quant 包可以被正确导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from quant.main import main

if __name__ == "__main__":
    main()
