"""
十一维量化交易系统 - 主入口

运行模式：
- daily: 每日收盘后运行，生成次日交易计划
- realtime: 盘中实时监控，信号触发提醒
- backtest: 历史回测
- score: 对指定股票进行十一维评分

用法：
    # 每日策略（收盘后运行）
    python quant/main.py --mode daily

    # 单票评分
    python quant/main.py --mode score --codes 603290 688017

    # 回测
    python quant/main.py --mode backtest --start 2024-01-01 --end 2024-12-31

    # 盘中监控
    python quant/main.py --mode realtime
"""

import argparse
import sys
import os
from datetime import date, datetime

from quant.engine.scorer import Scorer
from quant.engine.risk import RiskManager
from quant.engine.position import PositionManager
from quant.engine.universe import UniverseManager
from quant.execution.trader import Trader
from quant.data.provider import DataProvider


def run_daily():
    """
    每日策略模式

    流程：
    1. 加载股票池
    2. 获取市场情绪数据
    3. 风控检查
    4. 对股票池评分
    5. 生成调仓指令
    6. 输出交易计划
    """
    print("=" * 60)
    print(f"📅 每日策略 - {date.today()}")
    print("=" * 60)

    # 初始化组件
    universe = UniverseManager()
    scorer = Scorer()
    risk = RiskManager()
    position = PositionManager(risk)
    data = DataProvider()

    # 加载股票池
    # TODO: 从文件加载
    # universe.load_from_file("output/universe.json")
    print(f"\n📊 股票池: {universe.size} 只")

    if universe.size == 0:
        print("⚠️ 股票池为空，请先添加标的")
        print("   方法1: universe.load_from_file('output/universe.json')")
        print("   方法2: 手动添加 universe.add(StockInfo(...))")
        return

    # 获取情绪周期
    sentiment_signal = scorer.signals["d9_sentiment"]
    sentiment_result = sentiment_signal.compute("", date.today())
    phase = sentiment_result.details.get("phase", "neutral")
    print(f"\n🎭 情绪周期: {sentiment_result.details.get('phase_name', '未知')}")
    print(f"   操作纪律: {sentiment_result.details.get('trading_discipline', '')}")

    # 风控检查
    risk_check = risk.check_open("", phase, False)
    if not risk_check.can_open_new:
        print(f"\n⛔ 风控拦截，不允许开新仓:")
        for rule in risk_check.blocked_rules:
            print(f"   ❌ {rule}")
        return

    if risk_check.warnings:
        print(f"\n⚠️ 风控警告:")
        for w in risk_check.warnings:
            print(f"   ⚠️ {w}")

    # 对股票池评分
    print(f"\n📊 开始评分...")
    results = scorer.batch_score(universe.codes, date.today())

    # 输出评分结果
    print(f"\n📋 评分结果（前10）:")
    print(f"{'排名':<4} {'代码':<8} {'得分':<8} {'评级':<4} {'建议'}")
    print("-" * 60)
    for i, r in enumerate(results[:10], 1):
        print(f"{i:<4} {r.code:<8} {r.total_score:<8.1f} {r.rating:<4} {r.recommendation}")

    # 生成调仓指令
    orders = position.generate_orders(results, phase)
    if orders:
        print()
        position.print_orders(orders)
    else:
        print("\n📋 无需调仓")


def run_score(codes: list):
    """
    单票评分模式

    对指定股票进行完整的十一维评分
    """
    scorer = Scorer()

    for code in codes:
        print()
        result = scorer.score(code, date.today())
        scorer.print_report(result)


def run_realtime():
    """
    盘中实时监控模式

    持续监控：
    1. 持仓止损线
    2. 情绪周期变化
    3. 龙头状态变化
    4. 异常放量信号
    """
    print("=" * 60)
    print(f"🔴 实时监控模式 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    print("\n⚠️ 实时监控需要在交易时段运行（09:30-15:00）")
    print("   功能：")
    print("   - 持仓止损监控（铁律6）")
    print("   - 情绪周期实时判定")
    print("   - 龙头状态追踪")
    print("   - 异常放量提醒")
    print("\n   TODO: 接入实时数据流后启用")


def run_backtest(start: str, end: str):
    """
    回测模式
    """
    from quant.backtest.engine import BacktestEngine

    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)

    universe = UniverseManager()
    # TODO: 加载回测用股票池
    # universe.load_from_file("output/universe.json")

    if universe.size == 0:
        print("⚠️ 股票池为空，无法回测")
        print("   请先准备股票池文件: output/universe.json")
        return

    engine = BacktestEngine(
        universe=universe,
        start_date=start_date,
        end_date=end_date,
    )

    result = engine.run()
    return result


def main():
    parser = argparse.ArgumentParser(description="十一维量化交易系统")
    parser.add_argument(
        "--mode",
        choices=["daily", "realtime", "backtest", "score"],
        default="daily",
        help="运行模式",
    )
    parser.add_argument("--codes", nargs="+", help="股票代码列表（score模式）")
    parser.add_argument("--start", help="回测开始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", help="回测结束日期 (YYYY-MM-DD)")

    args = parser.parse_args()

    if args.mode == "daily":
        run_daily()
    elif args.mode == "score":
        if not args.codes:
            print("❌ score模式需要指定 --codes 参数")
            sys.exit(1)
        run_score(args.codes)
    elif args.mode == "realtime":
        run_realtime()
    elif args.mode == "backtest":
        if not args.start or not args.end:
            print("❌ backtest模式需要指定 --start 和 --end 参数")
            sys.exit(1)
        run_backtest(args.start, args.end)


if __name__ == "__main__":
    main()
