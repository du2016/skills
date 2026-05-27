"""
D11 国际形势信号（半自动）

半自动维度：
- 可量化部分：美元指数趋势、VIX恐慌指数、大宗商品价格
- 需人工部分：地缘事件、央视新闻解读

量化替代方案：
- 美元指数 DXY 趋势（走弱利好A股）
- VIX 恐慌指数（>30 为高风险）
- 人民币汇率趋势
- 黄金价格趋势（避险情绪指标）
"""

from datetime import date
from typing import Optional

from .base import MarketWideSignal, SignalResult


class GlobalSituationSignal(MarketWideSignal):
    dimension = "d11_global"
    max_score = 4.0
    description = "国际形势：外部环境对A股的影响"

    def compute_market(self, dt: Optional[date] = None) -> SignalResult:
        """
        国际形势综合评分

        子维度：
        1. 美元/汇率环境
        2. 全球风险偏好（VIX）
        3. 地缘政治事件（人工标注）
        4. 官媒信号（人工标注）
        """
        global_data = self._get_global_data(dt)

        sub_scores = {
            "usd_environment": self._score_usd(global_data),
            "risk_appetite": self._score_vix(global_data),
            "geopolitical": self._score_geopolitical(global_data),
            "official_media": self._score_media(global_data),
        }

        # 每个子维度 0-1 分，总计 0-4 分
        raw_score = sum(sub_scores.values())

        # 判断整体方向
        if raw_score >= 3.0:
            stance = "利好"
        elif raw_score >= 2.0:
            stance = "中性"
        else:
            stance = "利空"

        return self.make_result(
            raw_score=raw_score,
            confidence="medium",
            reason=f"国际形势{stance}（{raw_score:.1f}/4.0）",
            details={
                "sub_scores": sub_scores,
                "global_data": global_data,
                "stance": stance,
            },
        )

    def _get_global_data(self, dt: Optional[date] = None) -> dict:
        """
        获取全球宏观数据

        TODO: 接入外部数据源
        """
        return {
            "dxy": None,              # 美元指数
            "dxy_trend": None,        # 美元趋势 up/down/flat
            "vix": None,              # VIX恐慌指数
            "usdcny": None,           # 美元兑人民币
            "usdcny_trend": None,     # 汇率趋势
            "gold_trend": None,       # 黄金趋势
            "geopolitical_risk": 0,   # 地缘风险等级 0-5（人工标注）
            "media_signal": 0,        # 官媒信号 -2~+2（人工标注）
        }

    def _score_usd(self, data: dict) -> float:
        """
        美元/汇率环境评分 (0-1)

        美元走弱 + 人民币升值 → 1.0（利好A股）
        美元走强 + 人民币贬值 → 0.0（利空A股）
        """
        dxy_trend = data.get("dxy_trend")
        if dxy_trend == "down":
            return 1.0
        elif dxy_trend == "up":
            return 0.0
        return 0.5

    def _score_vix(self, data: dict) -> float:
        """
        全球风险偏好评分 (0-1)

        VIX < 15 → 1.0（风险偏好高）
        VIX 15-25 → 0.5（中性）
        VIX > 25 → 0.0（恐慌）
        """
        vix = data.get("vix")
        if vix is None:
            return 0.5
        if vix < 15:
            return 1.0
        elif vix > 25:
            return 0.0
        else:
            return 0.5

    def _score_geopolitical(self, data: dict) -> float:
        """
        地缘政治评分 (0-1)

        人工标注 geopolitical_risk: 0(无风险) ~ 5(极高风险)
        """
        risk = data.get("geopolitical_risk", 0)
        return max(0.0, 1.0 - risk * 0.2)

    def _score_media(self, data: dict) -> float:
        """
        官媒信号评分 (0-1)

        人工标注 media_signal: -2(强负面) ~ +2(强正面)
        """
        signal = data.get("media_signal", 0)
        return max(0.0, min(1.0, (signal + 2) / 4))
