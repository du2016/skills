"""
D6 未来潜力信号

量化替代方案：
- 一致预期营收增速（Wind/东财一致预期）
- 行业渗透率阶段
- PEG隐含增速 vs 实际增速
- 研发投入占比趋势
"""

from datetime import date
from typing import Optional

from .base import Signal, SignalResult
from ..data.provider import get_financials_data


class GrowthPotentialSignal(Signal):
    dimension = "d6_growth"
    max_score = 10.0
    description = "未来潜力：评估中长期成长空间"

    def compute(self, code: str, dt: Optional[date] = None) -> SignalResult:
        """
        成长潜力评分

        评分逻辑：
        - 一致预期3年复合增速 > 50% → 10分（十倍股潜力）
        - 一致预期3年复合增速 30-50% → 8分（三倍股潜力）
        - 一致预期3年复合增速 20-30% → 6分（翻倍潜力）
        - 一致预期3年复合增速 10-20% → 3分（稳健增长）
        - 一致预期3年复合增速 < 10% → 1分（价值修复）
        """
        growth_data = self._get_growth_data(code, dt)

        cagr_3y = growth_data.get("consensus_cagr_3y")
        if cagr_3y is None:
            return self.make_result(
                raw_score=3.0,
                confidence="low",
                reason="无一致预期数据，默认中性",
                details=growth_data,
            )

        # 映射得分
        if cagr_3y >= 0.50:
            raw_score = 10.0
            level = "十倍股潜力"
        elif cagr_3y >= 0.30:
            raw_score = 8.0
            level = "三倍股潜力"
        elif cagr_3y >= 0.20:
            raw_score = 6.0
            level = "翻倍潜力"
        elif cagr_3y >= 0.10:
            raw_score = 3.0
            level = "稳健增长"
        else:
            raw_score = 1.0
            level = "价值修复"

        # 加分项：渗透率处于加速期
        penetration = growth_data.get("penetration_rate")
        if penetration and 0.10 <= penetration <= 0.40:
            raw_score = min(10.0, raw_score + 1.0)
            level += "+渗透率加速"

        return self.make_result(
            raw_score=raw_score,
            confidence="medium",
            reason=f"一致预期3年CAGR={cagr_3y*100:.0f}%，{level}",
            details={
                **growth_data,
                "level": level,
            },
        )

    def _get_growth_data(self, code: str, dt: Optional[date] = None) -> dict:
        """获取成长性数据 — 聚宽财务指标"""
        data = {
            "consensus_cagr_3y": None,
            "revenue_current": None,
            "revenue_3y_target": None,
            "penetration_rate": None,
            "penetration_stage": None,
            "rd_ratio": None,
            "rd_trend": None,
            "new_business_contribution": None,
            "analyst_count": 0,
        }

        try:
            fin = get_financials_data(code, dt)
            # 用营收同比增速作为CAGR近似
            rev_growth = fin.get("revenue_growth_yoy")
            profit_growth = fin.get("profit_growth_yoy")

            # 取营收增速和利润增速中较高的作为成长性指标
            if rev_growth is not None and profit_growth is not None:
                data["consensus_cagr_3y"] = max(rev_growth, profit_growth)
            elif profit_growth is not None:
                data["consensus_cagr_3y"] = profit_growth
            elif rev_growth is not None:
                data["consensus_cagr_3y"] = rev_growth

            data["gross_margin"] = fin.get("gross_margin")
            data["roe"] = fin.get("roe")
        except Exception:
            pass

        return data
