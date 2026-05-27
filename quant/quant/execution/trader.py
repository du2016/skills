"""
交易执行器

职责：
1. 将仓位调整指令转化为具体订单
2. 控制执行时机（尾盘执行，符合铁律8）
3. 计算滑点和手续费
4. 预留券商API接口（QMT/掘金/聚宽）

当前实现：模拟执行（打印订单），不实际下单
"""

from datetime import datetime, time
from typing import List, Dict, Optional
from dataclasses import dataclass

from ..engine.position import PositionOrder
from ..config import BACKTEST_CONFIG, RISK_RULES


@dataclass
class ExecutionResult:
    """执行结果"""
    code: str
    action: str
    price: float
    shares: int
    amount: float
    commission: float
    stamp_tax: float
    slippage_cost: float
    total_cost: float
    success: bool
    message: str
    timestamp: datetime


class Trader:
    """交易执行器"""

    def __init__(self, mode: str = "simulation"):
        """
        Args:
            mode: simulation(模拟) / paper(模拟盘) / live(实盘)
        """
        self.mode = mode
        self._execution_log: List[ExecutionResult] = []

    def execute_orders(
        self,
        orders: List[PositionOrder],
        prices: Dict[str, float],
        total_capital: float,
    ) -> List[ExecutionResult]:
        """
        执行调仓指令

        Args:
            orders: 调仓指令列表
            prices: 当前价格 {code: price}
            total_capital: 总资金

        Returns:
            执行结果列表
        """
        # 检查执行时机（铁律8）
        now = datetime.now()
        decision_time = time(14, 30)

        if self.mode == "live" and now.time() < decision_time:
            print(f"⚠️ 铁律8：当前时间{now.strftime('%H:%M')}，"
                  f"建议在{RISK_RULES['decision_after_time']}后执行")
            # 非紧急订单延迟执行
            orders = [o for o in orders if o.urgency == "urgent"]
            if not orders:
                print("  无紧急订单，等待尾盘执行")
                return []

        results = []
        for order in orders:
            result = self._execute_single(order, prices, total_capital)
            results.append(result)
            self._execution_log.append(result)

        return results

    def _execute_single(
        self,
        order: PositionOrder,
        prices: Dict[str, float],
        total_capital: float,
    ) -> ExecutionResult:
        """执行单笔订单"""
        price = prices.get(order.code, 0)
        if price <= 0:
            return ExecutionResult(
                code=order.code,
                action=order.action,
                price=0,
                shares=0,
                amount=0,
                commission=0,
                stamp_tax=0,
                slippage_cost=0,
                total_cost=0,
                success=False,
                message=f"无法获取{order.code}的价格",
                timestamp=datetime.now(),
            )

        # 计算目标金额和股数
        target_amount = abs(order.delta_weight) * total_capital
        shares = self._round_shares(target_amount / price)

        if shares == 0:
            return ExecutionResult(
                code=order.code,
                action=order.action,
                price=price,
                shares=0,
                amount=0,
                commission=0,
                stamp_tax=0,
                slippage_cost=0,
                total_cost=0,
                success=False,
                message="计算股数为0，金额不足",
                timestamp=datetime.now(),
            )

        # 计算成本
        amount = shares * price
        slippage = amount * BACKTEST_CONFIG["slippage"]
        commission = max(5, amount * BACKTEST_CONFIG["commission_rate"])  # 最低5元

        # 印花税（仅卖出）
        stamp_tax = 0
        if order.action in ("sell", "reduce"):
            stamp_tax = amount * BACKTEST_CONFIG["stamp_tax"]

        total_cost = commission + stamp_tax + slippage

        # 模拟执行
        if self.mode == "simulation":
            success = True
            message = f"模拟执行成功"
        elif self.mode == "paper":
            success = self._paper_trade(order.code, order.action, shares, price)
            message = "模拟盘执行" if success else "模拟盘执行失败"
        elif self.mode == "live":
            success = self._live_trade(order.code, order.action, shares, price)
            message = "实盘执行" if success else "实盘执行失败"
        else:
            success = False
            message = f"未知模式: {self.mode}"

        return ExecutionResult(
            code=order.code,
            action=order.action,
            price=price,
            shares=shares,
            amount=amount,
            commission=commission,
            stamp_tax=stamp_tax,
            slippage_cost=slippage,
            total_cost=total_cost,
            success=success,
            message=message,
            timestamp=datetime.now(),
        )

    def _round_shares(self, shares: float) -> int:
        """
        股数取整（A股最小单位100股）
        """
        return int(shares // 100) * 100

    def _paper_trade(self, code: str, action: str, shares: int, price: float) -> bool:
        """
        模拟盘交易

        TODO: 接入模拟盘API（如聚宽模拟盘）
        """
        print(f"  [模拟盘] {action.upper()} {code} {shares}股 @ {price}")
        return True

    def _live_trade(self, code: str, action: str, shares: int, price: float) -> bool:
        """
        实盘交易

        TODO: 接入券商API
        支持的接口：
        - QMT（迅投）
        - 掘金量化
        - 聚宽
        - easytrader（非官方）
        """
        print(f"  ⚠️ [实盘] {action.upper()} {code} {shares}股 @ {price}")
        print(f"  ⚠️ 实盘接口未配置，请先接入券商API")
        return False

    def print_execution_summary(self, results: List[ExecutionResult]):
        """打印执行摘要"""
        if not results:
            print("📋 无执行记录")
            return

        print("=" * 60)
        print("📋 执行摘要")
        print("=" * 60)

        total_buy = 0
        total_sell = 0
        total_cost = 0

        for r in results:
            icon = "✅" if r.success else "❌"
            print(
                f"  {icon} {r.action.upper():<6} {r.code:<8} "
                f"{r.shares:>6}股 @ ¥{r.price:<8.2f} "
                f"金额:¥{r.amount:>10,.0f} "
                f"费用:¥{r.total_cost:>6,.0f} "
                f"| {r.message}"
            )

            if r.success:
                if r.action == "buy":
                    total_buy += r.amount
                elif r.action in ("sell", "reduce"):
                    total_sell += r.amount
                total_cost += r.total_cost

        print(f"\n  总买入: ¥{total_buy:,.0f}")
        print(f"  总卖出: ¥{total_sell:,.0f}")
        print(f"  总费用: ¥{total_cost:,.0f}")
        print("=" * 60)
