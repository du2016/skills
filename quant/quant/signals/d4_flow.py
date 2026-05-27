"""
D4 主力资金流信号（聚宽数据源）

数据源：聚宽 get_money_flow + get_mtss + get_billboard_list
"""

from datetime import date
from typing import Optional

from .base import Signal, SignalResult
from ..config import FLOW_CONFIG
from ..data.provider import get_money_flow_data, get_margin_data, get_billboard_data


class InstitutionalFlowSignal(Signal):
    dimension = "d4_flow"
    max_score = 10.0
    description = "主力资金流：跟踪聪明钱方向"

    def compute(self, code: str, dt: Optional[date] = None) -> SignalResult:
        """
        四路资金各给出方向：流入(+1) / 中性(0) / 流出(-1)
        - 主力资金流（大单净流入）
        - 融资余额趋势
        - 龙虎榜机构动向
        - 中单资金方向
        """
        flows = {
            "main_flow": self._check_main_flow(code, dt),
            "margin": self._check_margin_flow(code, dt),
            "billboard": self._check_billboard(code, dt),
            "mid_flow": self._check_mid_flow(code, dt),
        }

        inflow_count = sum(1 for v in flows.values() if v > 0)
        outflow_count = sum(1 for v in flows.values() if v < 0)

        if inflow_count >= 3:
            raw_score = 10.0
            resonance = "strong"
        elif inflow_count >= 2:
            raw_score = 7.0
            resonance = "weak"
        elif inflow_count >= 1 and outflow_count <= 1:
            raw_score = 4.0
            resonance = "single"
        elif inflow_count == 0 and outflow_count <= 1:
            raw_score = 2.0
            resonance = "neutral"
        else:
            raw_score = 0.0
            resonance = "divergent"

        return self.make_result(
            raw_score=raw_score,
            confidence="high" if any(v != 0 for v in flows.values()) else "low",
            reason=f"资金共振：{inflow_count}路流入/{outflow_count}路流出 → {resonance}",
            details={
                "flows": flows,
                "resonance": resonance,
                "inflow_count": inflow_count,
                "outflow_count": outflow_count,
            },
        )

    def _check_main_flow(self, code: str, dt: Optional[date] = None) -> int:
        """主力资金流方向（近5日累计）"""
        try:
            data = get_money_flow_data(code, days=10)
            if len(data) < 5:
                return 0
            recent_5 = data[-5:]
            total_main = sum(d["net_amount_main"] for d in recent_5)
            total_abs = sum(abs(d["net_amount_main"]) for d in recent_5)
            if total_abs == 0:
                return 0
            ratio = total_main / total_abs
            if ratio > 0.3:
                return 1
            elif ratio < -0.3:
                return -1
            return 0
        except Exception:
            return 0

    def _check_margin_flow(self, code: str, dt: Optional[date] = None) -> int:
        """融资余额趋势"""
        try:
            data = get_margin_data(code, days=10)
            if len(data) < 5:
                return 0
            recent = data[-5:]
            # 检查融资余额是否连续增加
            increasing = all(
                recent[i]["rzye"] >= recent[i - 1]["rzye"]
                for i in range(1, len(recent))
            )
            decreasing = all(
                recent[i]["rzye"] <= recent[i - 1]["rzye"]
                for i in range(1, len(recent))
            )
            if increasing:
                return 1
            elif decreasing:
                return -1
            return 0
        except Exception:
            return 0

    def _check_billboard(self, code: str, dt: Optional[date] = None) -> int:
        """龙虎榜净买入方向"""
        try:
            data = get_billboard_data(code, dt, lookback=10)
            if not data:
                return 0
            # 取最近一次上榜
            latest = data[0]
            if latest["net_value"] > 0:
                return 1
            elif latest["net_value"] < 0:
                return -1
            return 0
        except Exception:
            return 0

    def _check_mid_flow(self, code: str, dt: Optional[date] = None) -> int:
        """中单资金方向（散户跟风指标）"""
        try:
            data = get_money_flow_data(code, days=5)
            if len(data) < 3:
                return 0
            recent = data[-3:]
            total_mid = sum(d["net_amount_m"] for d in recent)
            if total_mid > 0:
                return 1
            elif total_mid < 0:
                return -1
            return 0
        except Exception:
            return 0
