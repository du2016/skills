"""
D3 选股信号：基本面筛选漏斗（聚宽数据源）

数据源：聚宽 get_fundamentals (valuation + indicator + balance + cash_flow)
"""

from datetime import date
from typing import Optional, Dict, List

from .base import Signal, SignalResult
from ..config import STOCK_FILTER
from ..data.provider import get_financials_data


class StockFilterSignal(Signal):
    dimension = "d3_stock"
    max_score = 12.0
    description = "基本面筛选：五层漏斗过滤"

    def compute(self, code: str, dt: Optional[date] = None) -> SignalResult:
        """对个股进行五层筛选"""
        fundamentals = get_financials_data(code, dt)
        passed_layers = []
        failed_layers = []

        # Layer 1: 行业地位（暂用市值代理）
        if self._check_industry_position(fundamentals):
            passed_layers.append("行业地位")
        else:
            failed_layers.append("行业地位")

        # Layer 2: 基本面
        if self._check_fundamentals(fundamentals):
            passed_layers.append("基本面")
        else:
            failed_layers.append("基本面")

        # Layer 3: 成长性
        if self._check_growth(fundamentals):
            passed_layers.append("成长性")
        else:
            failed_layers.append("成长性")

        # Layer 4: 估值
        if self._check_valuation(fundamentals):
            passed_layers.append("估值")
        else:
            failed_layers.append("估值")

        # Layer 5: 弹性
        if self._check_elasticity(fundamentals):
            passed_layers.append("弹性")
        else:
            failed_layers.append("弹性")

        layers_passed = len(passed_layers)
        score_map = {5: 12.0, 4: 10.0, 3: 7.0, 2: 4.0, 1: 2.0, 0: 0.0}
        raw_score = score_map.get(layers_passed, 0.0)

        return self.make_result(
            raw_score=raw_score,
            confidence="high" if fundamentals.get("roe") is not None else "low",
            reason=f"通过{layers_passed}/5层筛选：{', '.join(passed_layers)}" if passed_layers else "通过0/5层筛选",
            details={
                "passed_layers": passed_layers,
                "failed_layers": failed_layers,
                "fundamentals": fundamentals,
            },
        )

    def _check_industry_position(self, data: Dict) -> bool:
        """Layer 1: 行业地位 — 用市值>100亿近似龙头"""
        mcap = data.get("market_cap_yi", 0)
        return mcap >= 100

    def _check_fundamentals(self, data: Dict) -> bool:
        """Layer 2: 基本面 — ROE/负债率/现金流"""
        checks = []
        roe = data.get("roe")
        if roe is not None:
            checks.append(roe >= STOCK_FILTER["min_roe"])

        debt = data.get("debt_ratio")
        if debt is not None:
            checks.append(debt <= STOCK_FILTER["max_debt_ratio"])

        cf = data.get("operating_cashflow")
        if cf is not None:
            checks.append(cf > 0)

        pe = data.get("pe_ttm")
        if pe is not None and pe > 0:
            checks.append(pe < 150)

        if not checks:
            return False
        return sum(checks) >= max(1, len(checks) // 2)

    def _check_growth(self, data: Dict) -> bool:
        """Layer 3: 成长性 — 营收/利润增速"""
        rev_growth = data.get("revenue_growth_yoy")
        profit_growth = data.get("profit_growth_yoy")

        if rev_growth is not None and rev_growth >= 0.20:
            return True
        if profit_growth is not None and profit_growth >= 0.25:
            return True
        return False

    def _check_valuation(self, data: Dict) -> bool:
        """Layer 4: 估值 — PE合理"""
        pe = data.get("pe_ttm")
        if pe is None or pe <= 0:
            return False

        # 成长股：PE < 80 且有增长
        growth = data.get("profit_growth_yoy", 0) or 0
        if growth > 0:
            peg = pe / (growth * 100)
            return peg <= STOCK_FILTER["max_peg"]

        # 价值股：PE < 行业中位数（简化为<30）
        return pe < 30

    def _check_elasticity(self, data: Dict) -> bool:
        """Layer 5: 弹性 — 市值50-500亿"""
        mcap = data.get("market_cap_yi", 0)
        min_cap = STOCK_FILTER["min_market_cap"] / 1e8  # 转为亿
        max_cap = STOCK_FILTER["max_market_cap"] / 1e8
        return min_cap <= mcap <= max_cap


def batch_filter(codes: List[str], dt: Optional[date] = None) -> List[dict]:
    """批量筛选"""
    signal = StockFilterSignal()
    results = []
    for code in codes:
        result = signal.compute(code, dt)
        results.append({
            "code": code,
            "score": result.raw_score,
            "layers_passed": len(result.details.get("passed_layers", [])),
        })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results
