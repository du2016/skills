"""
回测引擎

职责：
1. 按日期回放历史数据
2. 模拟策略执行
3. 计算绩效指标
4. 输出回测报告
"""

from datetime import date, timedelta
from typing import Optional, List, Dict
from dataclasses import dataclass, field

from ..config import BACKTEST_CONFIG
from ..engine.scorer import Scorer
from ..engine.risk import RiskManager
from ..engine.position import PositionManager
from ..engine.universe import UniverseManager
from ..data.provider import DataProvider


@dataclass
class DailyRecord:
    """每日记录"""
    date: date
    total_value: float          # 总资产
    cash: float                 # 现金
    positions_value: float      # 持仓市值
    daily_return: float         # 日收益率
    benchmark_return: float     # 基准日收益率
    holdings: Dict[str, dict] = field(default_factory=dict)  # 持仓明细
    trades: List[dict] = field(default_factory=list)          # 当日交易


@dataclass
class BacktestResult:
    """回测结果"""
    start_date: date
    end_date: date
    initial_capital: float
    final_value: float
    total_return: float         # 总收益率
    annual_return: float        # 年化收益率
    max_drawdown: float         # 最大回撤
    sharpe_ratio: float         # 夏普比率
    win_rate: float             # 胜率
    profit_loss_ratio: float    # 盈亏比
    total_trades: int           # 总交易次数
    daily_records: List[DailyRecord] = field(default_factory=list)


class BacktestEngine:
    """回测引擎"""

    def __init__(
        self,
        universe: UniverseManager,
        start_date: date,
        end_date: date,
        initial_capital: float = None,
    ):
        self.universe = universe
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital or BACKTEST_CONFIG["initial_capital"]

        # 组件
        self.data = DataProvider()
        self.scorer = Scorer()
        self.risk = RiskManager()
        self.position = PositionManager(self.risk)

        # 状态
        self._cash = self.initial_capital
        self._holdings: Dict[str, dict] = {}  # code -> {shares, cost, value}
        self._daily_records: List[DailyRecord] = []
        self._all_trades: List[dict] = []

    def run(self) -> BacktestResult:
        """
        运行回测

        按交易日逐日回放：
        1. 更新持仓市值
        2. 检查止损
        3. 计算信号和评分
        4. 生成调仓指令
        5. 模拟执行
        6. 记录当日数据
        """
        print(f"🚀 开始回测: {self.start_date} → {self.end_date}")
        print(f"   初始资金: ¥{self.initial_capital:,.0f}")
        print(f"   股票池: {self.universe.size} 只")
        print()

        trading_days = self._get_trading_days()
        print(f"   交易日数: {len(trading_days)}")

        for i, dt in enumerate(trading_days):
            self._process_day(dt)

            # 进度显示
            if (i + 1) % 20 == 0:
                total_value = self._get_total_value()
                ret = (total_value - self.initial_capital) / self.initial_capital
                print(f"   [{dt}] 总资产: ¥{total_value:,.0f} 收益: {ret*100:+.2f}%")

        # 计算绩效
        result = self._calculate_performance()
        self._print_result(result)
        return result

    def _process_day(self, dt: date):
        """处理单个交易日"""
        # 1. 获取当日价格，更新持仓市值
        prices = self._get_prices(dt)
        self._update_holdings_value(prices)

        # 2. 检查止损
        stop_loss_orders = self.position.generate_stop_loss_orders(prices)
        if stop_loss_orders:
            self._execute_orders(stop_loss_orders, prices, dt)

        # 3. 每周一重新评分（降低交易频率）
        # 实际可以改为每日，但频繁交易会增加成本
        if dt.weekday() == 0:  # 周一
            self._rebalance(dt, prices)

        # 4. 记录当日数据
        self._record_day(dt, prices)

    def _rebalance(self, dt: date, prices: Dict[str, float]):
        """再平衡"""
        # 获取情绪周期
        sentiment_result = self.scorer.signals["d9_sentiment"].compute("", dt)
        sentiment_phase = sentiment_result.details.get("phase", "neutral")

        # 获取板块割裂度
        leader_signal = self.scorer.signals["d10_leader"]
        split_info = leader_signal.get_market_split_degree(dt)
        sector_split = split_info.get("split_degree", 0) > 0.6

        # 风控检查
        risk_check = self.risk.check_open("", sentiment_phase, sector_split)
        if not risk_check.can_open_new:
            return  # 风控不允许开仓

        # 对股票池评分
        codes = self.universe.codes
        scoring_results = self.scorer.batch_score(codes, dt)

        # 生成调仓指令
        current_weights = {
            code: info["value"] / self._get_total_value()
            for code, info in self._holdings.items()
            if self._get_total_value() > 0
        }
        self.position.update_holdings(current_weights)
        self.position.set_capital(self._get_total_value())

        orders = self.position.generate_orders(
            scoring_results, sentiment_phase, sector_split
        )

        # 执行
        if orders:
            self._execute_orders(orders, prices, dt)

    def _execute_orders(self, orders, prices: Dict[str, float], dt: date):
        """模拟执行订单"""
        for order in orders:
            price = prices.get(order.code, 0)
            if price <= 0:
                continue

            total_value = self._get_total_value()
            target_amount = abs(order.delta_weight) * total_value

            if order.action == "buy":
                shares = int(target_amount / price // 100) * 100
                if shares <= 0:
                    continue
                cost = shares * price * (1 + BACKTEST_CONFIG["slippage"])
                commission = max(5, cost * BACKTEST_CONFIG["commission_rate"])
                total_cost = cost + commission

                if total_cost > self._cash:
                    continue

                self._cash -= total_cost
                if order.code in self._holdings:
                    # 加仓
                    h = self._holdings[order.code]
                    total_shares = h["shares"] + shares
                    avg_cost = (h["cost"] * h["shares"] + price * shares) / total_shares
                    h["shares"] = total_shares
                    h["cost"] = avg_cost
                    h["value"] = total_shares * price
                else:
                    self._holdings[order.code] = {
                        "shares": shares,
                        "cost": price,
                        "value": shares * price,
                    }

                self._all_trades.append({
                    "date": dt,
                    "code": order.code,
                    "action": "buy",
                    "price": price,
                    "shares": shares,
                    "amount": cost,
                })

            elif order.action in ("sell", "reduce"):
                if order.code not in self._holdings:
                    continue

                h = self._holdings[order.code]
                if order.action == "sell":
                    shares = h["shares"]
                else:
                    shares = min(
                        int(target_amount / price // 100) * 100,
                        h["shares"],
                    )

                if shares <= 0:
                    continue

                proceeds = shares * price * (1 - BACKTEST_CONFIG["slippage"])
                commission = max(5, proceeds * BACKTEST_CONFIG["commission_rate"])
                stamp_tax = proceeds * BACKTEST_CONFIG["stamp_tax"]
                net_proceeds = proceeds - commission - stamp_tax

                self._cash += net_proceeds
                h["shares"] -= shares
                if h["shares"] <= 0:
                    del self._holdings[order.code]
                else:
                    h["value"] = h["shares"] * price

                pnl = (price - h["cost"]) / h["cost"]
                self._all_trades.append({
                    "date": dt,
                    "code": order.code,
                    "action": "sell",
                    "price": price,
                    "shares": shares,
                    "amount": proceeds,
                    "pnl": pnl,
                })

    def _get_prices(self, dt: date) -> Dict[str, float]:
        """获取当日收盘价"""
        # TODO: 从历史数据获取
        return {}

    def _update_holdings_value(self, prices: Dict[str, float]):
        """更新持仓市值"""
        for code, holding in self._holdings.items():
            if code in prices:
                holding["value"] = holding["shares"] * prices[code]

    def _get_total_value(self) -> float:
        """计算总资产"""
        positions_value = sum(h["value"] for h in self._holdings.values())
        return self._cash + positions_value

    def _record_day(self, dt: date, prices: Dict[str, float]):
        """记录当日数据"""
        total_value = self._get_total_value()
        positions_value = sum(h["value"] for h in self._holdings.values())

        prev_value = (
            self._daily_records[-1].total_value
            if self._daily_records
            else self.initial_capital
        )
        daily_return = (total_value - prev_value) / prev_value if prev_value > 0 else 0

        self._daily_records.append(DailyRecord(
            date=dt,
            total_value=total_value,
            cash=self._cash,
            positions_value=positions_value,
            daily_return=daily_return,
            benchmark_return=0,  # TODO: 接入基准指数
            holdings=dict(self._holdings),
        ))

    def _get_trading_days(self) -> List[date]:
        """
        获取交易日列表

        TODO: 接入真实交易日历
        简化实现：排除周末
        """
        days = []
        current = self.start_date
        while current <= self.end_date:
            if current.weekday() < 5:  # 排除周末
                days.append(current)
            current += timedelta(days=1)
        return days

    def _calculate_performance(self) -> BacktestResult:
        """计算绩效指标"""
        if not self._daily_records:
            return BacktestResult(
                start_date=self.start_date,
                end_date=self.end_date,
                initial_capital=self.initial_capital,
                final_value=self.initial_capital,
                total_return=0,
                annual_return=0,
                max_drawdown=0,
                sharpe_ratio=0,
                win_rate=0,
                profit_loss_ratio=0,
                total_trades=0,
            )

        final_value = self._daily_records[-1].total_value
        total_return = (final_value - self.initial_capital) / self.initial_capital

        # 年化收益率
        days = (self.end_date - self.start_date).days
        annual_return = (1 + total_return) ** (365 / max(days, 1)) - 1

        # 最大回撤
        max_drawdown = self._calc_max_drawdown()

        # 夏普比率（假设无风险利率2%）
        sharpe_ratio = self._calc_sharpe(annual_return)

        # 胜率和盈亏比
        sell_trades = [t for t in self._all_trades if t["action"] == "sell" and "pnl" in t]
        wins = [t for t in sell_trades if t["pnl"] > 0]
        losses = [t for t in sell_trades if t["pnl"] < 0]

        win_rate = len(wins) / len(sell_trades) if sell_trades else 0
        avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
        avg_loss = abs(sum(t["pnl"] for t in losses) / len(losses)) if losses else 1
        profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0

        return BacktestResult(
            start_date=self.start_date,
            end_date=self.end_date,
            initial_capital=self.initial_capital,
            final_value=final_value,
            total_return=total_return,
            annual_return=annual_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            win_rate=win_rate,
            profit_loss_ratio=profit_loss_ratio,
            total_trades=len(self._all_trades),
            daily_records=self._daily_records,
        )

    def _calc_max_drawdown(self) -> float:
        """计算最大回撤"""
        peak = 0
        max_dd = 0
        for record in self._daily_records:
            if record.total_value > peak:
                peak = record.total_value
            dd = (peak - record.total_value) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        return max_dd

    def _calc_sharpe(self, annual_return: float, risk_free: float = 0.02) -> float:
        """计算夏普比率"""
        if not self._daily_records:
            return 0

        returns = [r.daily_return for r in self._daily_records]
        if not returns:
            return 0

        import math
        avg_return = sum(returns) / len(returns)
        variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
        std = math.sqrt(variance) if variance > 0 else 0
        annual_std = std * math.sqrt(252)

        if annual_std == 0:
            return 0
        return (annual_return - risk_free) / annual_std

    def _print_result(self, result: BacktestResult):
        """打印回测结果"""
        print("\n" + "=" * 60)
        print("📊 回测结果")
        print("=" * 60)
        print(f"  回测区间: {result.start_date} → {result.end_date}")
        print(f"  初始资金: ¥{result.initial_capital:,.0f}")
        print(f"  最终资产: ¥{result.final_value:,.0f}")
        print(f"  总收益率: {result.total_return*100:+.2f}%")
        print(f"  年化收益: {result.annual_return*100:+.2f}%")
        print(f"  最大回撤: {result.max_drawdown*100:.2f}%")
        print(f"  夏普比率: {result.sharpe_ratio:.2f}")
        print(f"  胜率:     {result.win_rate*100:.1f}%")
        print(f"  盈亏比:   {result.profit_loss_ratio:.2f}")
        print(f"  总交易数: {result.total_trades}")
        print("=" * 60)
