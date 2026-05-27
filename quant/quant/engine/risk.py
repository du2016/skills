"""
风控规则引擎

编码8条铁律为硬性规则，任何信号都无法覆盖。
"""

from datetime import date, datetime, time
from typing import Optional, List, Dict
from dataclasses import dataclass, field

from ..config import RISK_RULES


@dataclass
class RiskCheckResult:
    """风控检查结果"""
    passed: bool                    # 是否通过风控
    blocked_rules: List[str] = field(default_factory=list)  # 触发的规则
    warnings: List[str] = field(default_factory=list)       # 警告（不阻断）
    max_position: float = 1.0       # 允许的最大总仓位
    can_open_new: bool = True       # 是否允许开新仓


@dataclass
class TradeRecord:
    """交易记录（用于铁律7判断）"""
    code: str
    date: date
    direction: str  # buy / sell
    pnl: float      # 盈亏比例


class RiskManager:
    """风控管理器"""

    def __init__(self):
        self._trade_history: List[TradeRecord] = []
        self._holdings: Dict[str, dict] = {}  # code -> {cost, shares, date}

    def add_trade(self, record: TradeRecord):
        """记录交易"""
        self._trade_history.append(record)

    def update_holding(self, code: str, cost: float, shares: int, entry_date: date):
        """更新持仓"""
        if shares > 0:
            self._holdings[code] = {
                "cost": cost,
                "shares": shares,
                "entry_date": entry_date,
            }
        elif code in self._holdings:
            del self._holdings[code]

    def check_open(
        self,
        code: str,
        sentiment_phase: str,
        sector_split: bool,
        current_time: Optional[datetime] = None,
    ) -> RiskCheckResult:
        """
        开仓前风控检查

        检查所有铁律是否允许开仓
        """
        result = RiskCheckResult(passed=True)
        now = current_time or datetime.now()

        # 铁律1：冰点期不开仓
        if RISK_RULES["no_open_in_freeze"] and sentiment_phase == "freeze":
            result.passed = False
            result.can_open_new = False
            result.blocked_rules.append("铁律1：冰点期不开新仓")

        # 铁律2：退潮期不抄底
        if RISK_RULES["no_buy_in_retreat"] and sentiment_phase == "retreat":
            result.passed = False
            result.can_open_new = False
            result.blocked_rules.append("铁律2：退潮期不抄底，不接飞刀")

        # 铁律4：板块割裂时降仓
        if RISK_RULES["reduce_on_split"] and sector_split:
            result.max_position = RISK_RULES["split_max_position"]
            result.warnings.append(
                f"铁律4：板块割裂，最大仓位降至{result.max_position*100:.0f}%"
            )

        # 铁律7：连续亏损后休息
        if self._check_consecutive_losses():
            result.passed = False
            result.can_open_new = False
            result.blocked_rules.append(
                f"铁律7：连续亏损{RISK_RULES['max_consecutive_losses']}次，"
                f"强制休息{RISK_RULES['rest_days_after_loss']}天"
            )

        # 铁律8：尾盘决策
        decision_time = time(14, 30)
        if now.time() < decision_time:
            result.warnings.append(
                f"铁律8：建议在{RISK_RULES['decision_after_time']}后做决策"
            )

        return result

    def check_holding(self, code: str, current_price: float) -> RiskCheckResult:
        """
        持仓风控检查

        主要检查止损线
        """
        result = RiskCheckResult(passed=True)

        holding = self._holdings.get(code)
        if not holding:
            return result

        # 铁律6：单票止损
        cost = holding["cost"]
        pnl = (current_price - cost) / cost

        if pnl <= RISK_RULES["stop_loss_pct"]:
            result.passed = False
            result.blocked_rules.append(
                f"铁律6：{code}亏损{pnl*100:.1f}%，"
                f"触及止损线{RISK_RULES['stop_loss_pct']*100:.0f}%，无条件止损"
            )

        # 警告：接近止损线
        elif pnl <= RISK_RULES["stop_loss_pct"] * 0.7:
            result.warnings.append(
                f"警告：{code}亏损{pnl*100:.1f}%，接近止损线"
            )

        return result

    def check_all_holdings(self, prices: Dict[str, float]) -> List[RiskCheckResult]:
        """检查所有持仓的风控状态"""
        results = []
        for code in self._holdings:
            if code in prices:
                result = self.check_holding(code, prices[code])
                if not result.passed or result.warnings:
                    results.append(result)
        return results

    def _check_consecutive_losses(self) -> bool:
        """
        检查是否连续亏损达到阈值

        铁律7：连续亏损2次后强制休息1天
        """
        max_losses = RISK_RULES["max_consecutive_losses"]

        if len(self._trade_history) < max_losses:
            return False

        # 取最近N笔卖出交易
        recent_sells = [
            t for t in self._trade_history
            if t.direction == "sell"
        ][-max_losses:]

        if len(recent_sells) < max_losses:
            return False

        # 检查是否全部亏损
        all_loss = all(t.pnl < 0 for t in recent_sells)

        if all_loss:
            # 检查是否已经休息了足够天数
            last_loss_date = recent_sells[-1].date
            rest_days = (date.today() - last_loss_date).days
            return rest_days < RISK_RULES["rest_days_after_loss"]

        return False

    def get_max_new_position(
        self, sentiment_phase: str, sector_split: bool
    ) -> float:
        """
        计算当前允许的最大新开仓位

        综合考虑：
        - 情绪周期对应的仓位上限
        - 板块割裂的仓位限制
        - 已有持仓占用
        """
        from ..config import POSITION_CONFIG, MACRO_CONFIG

        # 基础上限
        max_total = POSITION_CONFIG["max_total_position"]

        # 情绪周期调整
        phase_multiplier = {
            "freeze": 0.0,
            "retreat": 0.0,
            "neutral": 0.6,
            "warming": 0.8,
            "climax": 1.0,
        }
        max_total *= phase_multiplier.get(sentiment_phase, 0.6)

        # 板块割裂调整
        if sector_split:
            max_total = min(max_total, RISK_RULES["split_max_position"])

        # 减去已有持仓
        current_position = self._get_current_total_position()
        available = max(0, max_total - current_position)

        return available

    def _get_current_total_position(self) -> float:
        """计算当前总仓位占比"""
        # TODO: 需要接入账户总资产数据
        return 0.0
