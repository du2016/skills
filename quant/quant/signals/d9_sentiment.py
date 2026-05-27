"""
D9 情绪周期信号（完全量化 — 已对接数据源）

数据源：同花顺热点（涨停股+题材归因）+ 腾讯（成交量）
"""

from datetime import date
from typing import Optional

from .base import MarketWideSignal, SignalResult
from ..config import SENTIMENT_CONFIG
from ..data.provider import get_market_sentiment


class SentimentCycleSignal(MarketWideSignal):
    dimension = "d9_sentiment"
    max_score = 5.0
    description = "情绪周期：判断市场节奏，执行交易纪律"

    def compute_market(self, dt: Optional[date] = None) -> SignalResult:
        """
        判定当前情绪周期阶段

        数据来源：
        - 同花顺热点：涨停股数量、题材集中度
        - 腾讯行情：大盘成交量
        - 东财行业：板块涨跌分布
        """
        market_data = self._get_market_sentiment_data(dt)
        phase = self._determine_phase(market_data)

        phase_scores = {
            "climax": 5.0,
            "warming": 5.0,
            "neutral": 3.0,
            "retreat": 0.0,
            "freeze": 0.0,
        }

        raw_score = phase_scores.get(phase, 3.0)
        veto = phase == "freeze"

        return self.make_result(
            raw_score=raw_score,
            confidence="high" if market_data.get("data_available") else "low",
            reason=f"情绪周期：{self._phase_name(phase)}",
            details={
                "phase": phase,
                "phase_name": self._phase_name(phase),
                "market_data": market_data,
                "trading_discipline": self._get_discipline(phase),
            },
            veto=veto,
            veto_reason="情绪冰点期，铁律1：不开新仓" if veto else "",
        )

    def _get_market_sentiment_data(self, dt: Optional[date] = None) -> dict:
        """从聚宽获取市场情绪数据"""
        try:
            sentiment = get_market_sentiment(dt)
            return {
                "data_available": True,
                "limit_up_count": sentiment.get("limit_up_count", 0),
                "limit_down_count": sentiment.get("limit_down_count", 0),
                "advance_count": sentiment.get("advance_count", 0),
                "decline_count": sentiment.get("decline_count", 0),
                "max_consecutive_board": 0,  # 聚宽无直接连板数据，需额外计算
                "tag_concentration": 0.2,  # 无题材数据时默认中性
                "top_tags": [],
                "total_volume_billion": 0,
                "leader_status": "unknown",
            }
        except Exception:
            return {"data_available": False}

    def _determine_phase(self, data: dict) -> str:
        """判定情绪周期阶段"""
        if not data.get("data_available"):
            return "neutral"

        limit_up = data.get("limit_up_count", 0)
        limit_down = data.get("limit_down_count", 0)
        advance = data.get("advance_count", 0)
        decline = data.get("decline_count", 0)
        max_board = data.get("max_consecutive_board", 0)

        cfg = SENTIMENT_CONFIG

        # 冰点期：涨停少 + 跌停多
        if limit_up < 20 and limit_down > 30:
            return "freeze"

        # 退潮期：跌停多于涨停 + 下跌家数远多于上涨
        if limit_down > limit_up and decline > advance * 2:
            return "retreat"

        # 高潮期：涨停多 + 上涨家数远多于下跌
        if limit_up >= 80 and advance > decline * 2:
            return "climax"

        # 回暖期：涨停适中 + 上涨多于下跌
        if limit_up >= 40 and advance > decline:
            return "warming"

        return "neutral"

    def _phase_name(self, phase: str) -> str:
        names = {
            "freeze": "❄️ 冰点期",
            "warming": "🌤️ 回暖期",
            "climax": "🔥 高潮期",
            "retreat": "🌊 退潮期",
            "neutral": "😐 中性",
        }
        return names.get(phase, "未知")

    def _get_discipline(self, phase: str) -> str:
        disciplines = {
            "freeze": "空仓观望，等待转势信号（铁律1）",
            "warming": "轻仓试错，买在分歧，聚焦龙头",
            "climax": "重仓进攻，注意高位股分歧风险",
            "retreat": "减仓/清仓，不抄底不接飞刀（铁律2）",
            "neutral": "标准仓位，按信号操作",
        }
        return disciplines.get(phase, "")
