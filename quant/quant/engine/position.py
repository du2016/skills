"""
仓位管理器

职责：
1. 根据评分和风控结果确定目标仓位
2. 生成调仓指令（买入/卖出/持有）
3. 控制单票和总仓位上限
"""

from datetime import date
from typing import Optional, List, Dict
from dataclasses import dataclass

from ..config import POSITION_CONFIG
from .scorer import ScoringResult
from .risk import RiskManager, RiskCheckResult


@dataclass
class PositionOrder:
    """仓位调整指令"""
    code: str
    action: str             # buy / sell / hold / reduce
    target_weight: float    # 目标仓位权重 (0-1)
    current_weight: float   # 当前仓位权重
    delta_weight: float     # 变动量
    reason: str
    priority: int = 0       # 优先级（越高越先执行）
    urgency: str = "normal"  # urgent(止损) / normal / low


class PositionManager:
    """仓位管理器"""

    def __init__(self, risk_manager: RiskManager):
        self.risk = risk_manager
        self._current_holdings: Dict[str, float] = {}  # code -> weight
        self._total_capital: float = 0.0

    def set_capital(self, capital: float):
        """设置总资金"""
        self._total_capital = capital

    def update_holdings(self, holdings: Dict[str, float]):
        """更新当前持仓权重"""
        self._current_holdings = holdings.copy()

    def generate_orders(
        self,
        scoring_results: List[ScoringResult],
        sentiment_phase: str,
        sector_split: bool = False,
    ) -> List[PositionOrder]:
        """
        根据评分结果生成调仓指令

        流程：
        1. 确定可用仓位上限
        2. 对评分结果排序
        3. 分配目标仓位
        4. 与当前持仓对比，生成调仓指令
        """
        orders = []

        # Step 1: 确定仓位上限
        max_available = self.risk.get_max_new_position(
            sentiment_phase, sector_split
        )

        # Step 2: 筛选可操作的标的（未被否决 + 评级>=B）
        actionable = [
            r for r in scoring_results
            if not r.vetoed and r.rating in ("S", "A", "B")
        ]

        # 按得分排序
        actionable.sort(key=lambda x: -x.total_score)

        # 限制最大持仓数
        max_holdings = POSITION_CONFIG["max_holdings"]
        actionable = actionable[:max_holdings]

        # Step 3: 分配目标仓位
        target_weights = self._allocate_weights(actionable, max_available)

        # Step 4: 生成调仓指令
        # 4a: 需要卖出的（当前持有但不在目标中）
        for code, current_weight in self._current_holdings.items():
            if code not in target_weights:
                orders.append(PositionOrder(
                    code=code,
                    action="sell",
                    target_weight=0.0,
                    current_weight=current_weight,
                    delta_weight=-current_weight,
                    reason="不在目标持仓中，清仓",
                    priority=10,
                ))

        # 4b: 需要买入或调整的
        for code, target_weight in target_weights.items():
            current_weight = self._current_holdings.get(code, 0.0)
            delta = target_weight - current_weight

            if abs(delta) < 0.01:
                # 变动太小，忽略
                continue

            if delta > 0:
                action = "buy"
                reason = f"目标仓位{target_weight*100:.0f}%，需加仓{delta*100:.0f}%"
            else:
                action = "reduce"
                reason = f"目标仓位{target_weight*100:.0f}%，需减仓{abs(delta)*100:.0f}%"

            orders.append(PositionOrder(
                code=code,
                action=action,
                target_weight=target_weight,
                current_weight=current_weight,
                delta_weight=delta,
                reason=reason,
                priority=5 if action == "buy" else 8,
            ))

        # 按优先级排序（卖出优先于买入，释放资金）
        orders.sort(key=lambda x: -x.priority)

        return orders

    def generate_stop_loss_orders(
        self, prices: Dict[str, float]
    ) -> List[PositionOrder]:
        """
        生成止损指令（最高优先级）

        铁律6：单票亏损>7%无条件止损
        """
        orders = []
        risk_results = self.risk.check_all_holdings(prices)

        for result in risk_results:
            if not result.passed:
                for rule in result.blocked_rules:
                    if "止损" in rule:
                        # 提取股票代码（从规则描述中）
                        # 实际实现中应该直接传递code
                        orders.append(PositionOrder(
                            code="",  # TODO: 从risk result中获取
                            action="sell",
                            target_weight=0.0,
                            current_weight=0.0,
                            delta_weight=0.0,
                            reason=rule,
                            priority=100,  # 最高优先级
                            urgency="urgent",
                        ))

        return orders

    def _allocate_weights(
        self, results: List[ScoringResult], max_total: float
    ) -> Dict[str, float]:
        """
        仓位分配算法

        策略：
        - S级：取仓位范围上限
        - A级：取仓位范围中值
        - B级：取仓位范围下限
        - 总和不超过 max_total
        """
        target_weights = {}
        remaining = max_total

        for result in results:
            if remaining <= 0:
                break

            pos_range = result.position_range
            # 根据评级选择仓位
            if result.rating == "S":
                weight = pos_range[1]  # 上限
            elif result.rating == "A":
                weight = (pos_range[0] + pos_range[1]) / 2  # 中值
            else:
                weight = pos_range[0]  # 下限

            # 不超过单票上限
            weight = min(weight, POSITION_CONFIG["max_single_position"])
            # 不超过剩余可用
            weight = min(weight, remaining)

            if weight > 0.01:
                target_weights[result.code] = weight
                remaining -= weight

        return target_weights

    def print_orders(self, orders: List[PositionOrder]):
        """打印调仓指令"""
        if not orders:
            print("📋 无需调仓")
            return

        print("=" * 60)
        print("📋 调仓指令")
        print("=" * 60)

        for order in orders:
            icon = {
                "buy": "🟢",
                "sell": "🔴",
                "reduce": "🟡",
                "hold": "⚪",
            }.get(order.action, "⚪")

            urgency_mark = "⚡" if order.urgency == "urgent" else ""

            print(
                f"  {urgency_mark}{icon} {order.action.upper():<6} "
                f"{order.code:<8} "
                f"目标:{order.target_weight*100:>5.1f}% "
                f"变动:{order.delta_weight*100:>+5.1f}% "
                f"| {order.reason}"
            )

        print("=" * 60)
