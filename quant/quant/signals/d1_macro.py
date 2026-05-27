"""
D1 宏观择时信号

量化指标：
- 经济周期：PMI、社融增速、M1-M2剪刀差
- 流动性：DR007、十年期国债收益率、北向资金趋势
- 市场估值：沪深300 PE分位数
- 成交量趋势：两市成交额MA5 vs MA20

输出：系统性仓位系数（决定整体仓位上限）
"""

from datetime import date
from typing import Optional

from .base import MarketWideSignal, SignalResult


class MacroTimingSignal(MarketWideSignal):
    dimension = "d1_macro"
    max_score = 15.0
    description = "宏观择时：决定系统性仓位上限"

    def compute_market(self, dt: Optional[date] = None) -> SignalResult:
        """
        宏观择时综合评分

        四个子维度各给出 利多(+1) / 中性(0) / 利空(-1)：
        1. 经济周期
        2. 流动性环境
        3. 全球联动
        4. 市场情绪与估值
        """
        scores = {
            "economic_cycle": self._score_economic_cycle(dt),
            "liquidity": self._score_liquidity(dt),
            "global_linkage": self._score_global(dt),
            "market_sentiment": self._score_sentiment(dt),
        }

        # 统计利多数量
        bullish_count = sum(1 for v in scores.values() if v > 0)
        bearish_count = sum(1 for v in scores.values() if v < 0)

        # 映射到得分
        if bullish_count >= 4:
            raw_score = 15.0
            stance = "aggressive"
        elif bullish_count >= 3:
            raw_score = 12.0
            stance = "aggressive"
        elif bullish_count >= 2 and bearish_count <= 1:
            raw_score = 9.0
            stance = "balanced"
        elif bullish_count >= 1:
            raw_score = 5.0
            stance = "balanced"
        else:
            raw_score = 0.0
            stance = "defensive"

        return self.make_result(
            raw_score=raw_score,
            confidence="medium",
            reason=f"宏观环境：{bullish_count}个利多/{bearish_count}个利空 → {stance}",
            details={
                "sub_scores": scores,
                "stance": stance,
                "bullish_count": bullish_count,
                "bearish_count": bearish_count,
            },
        )

    def _score_economic_cycle(self, dt: Optional[date] = None) -> int:
        """
        经济周期评分
        PMI > 50 且趋势向上 → +1
        PMI < 49 且趋势向下 → -1
        其他 → 0

        TODO: 接入实际数据源（国家统计局/Wind）
        """
        # 占位实现：返回中性
        # 实际实现需要：
        # 1. 获取最新PMI数据
        # 2. 获取社融增速
        # 3. 计算M1-M2剪刀差趋势
        return 0

    def _score_liquidity(self, dt: Optional[date] = None) -> int:
        """
        流动性评分
        DR007 < 政策利率 且 十年期国债收益率下行 → +1
        DR007 > 政策利率+50bp → -1
        其他 → 0

        TODO: 接入实际数据源
        """
        return 0

    def _score_global(self, dt: Optional[date] = None) -> int:
        """
        全球联动评分
        美联储降息周期 + 美元走弱 → +1
        美联储加息 + 美元走强 + 地缘风险升级 → -1
        其他 → 0

        TODO: 接入实际数据源
        """
        return 0

    def _score_sentiment(self, dt: Optional[date] = None) -> int:
        """
        市场情绪与估值评分
        沪深300 PE分位 < 30% + 成交量MA5 > MA20 → +1
        沪深300 PE分位 > 80% + 成交量萎缩 → -1
        其他 → 0

        TODO: 接入实际数据源
        """
        return 0
