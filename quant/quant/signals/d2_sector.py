"""
D2 赛道轮动信号（聚宽数据源）

数据源：聚宽 get_industry + 行业指数涨跌排名
"""

from datetime import date
from typing import Optional, List, Dict

from .base import Signal, SignalResult
from ..config import SECTOR_CONFIG
from ..data.provider import get_stock_industry, get_industry_ranking


class SectorRotationSignal(Signal):
    dimension = "d2_sector"
    max_score = 12.0
    description = "赛道轮动：识别当前最强赛道"

    def compute(self, code: str, dt: Optional[date] = None) -> SignalResult:
        """判断个股所在赛道的强弱"""
        # 1. 获取个股所属行业
        industry_info = get_stock_industry(code, dt)
        sector = industry_info.get("sw_l1", "")

        if not sector:
            return self.make_result(
                raw_score=4.0,
                confidence="low",
                reason=f"未获取到行业分类，默认中性",
                details={"sector": sector},
            )

        # 2. 获取行业排名
        sectors = get_industry_ranking(dt)
        total_sectors = len(sectors)

        # 3. 找到该行业的排名
        sector_info = None
        for s in sectors:
            if s["name"] == sector or sector in s["name"] or s["name"] in sector:
                sector_info = s
                break

        if sector_info is None:
            return self.make_result(
                raw_score=4.0,
                confidence="low",
                reason=f"行业[{sector}]未在排名中找到，默认中性",
                details={"sector": sector, "top_sectors": sectors[:5]},
            )

        # 4. 综合评分：排名分 + 涨幅分
        rank = sector_info["rank"]
        change_pct = sector_info.get("change_pct", 0)

        if total_sectors > 0:
            percentile = 1 - (rank - 1) / total_sectors
        else:
            percentile = 0.5
        rank_score = percentile * 2.5

        if change_pct >= 3:
            change_score = 2.5
        elif change_pct >= 1:
            change_score = 2.0
        elif change_pct >= 0:
            change_score = 1.5
        elif change_pct >= -1:
            change_score = 1.0
        elif change_pct >= -2:
            change_score = 0.5
        else:
            change_score = 0.0

        sector_score = rank_score + change_score

        if sector_score >= 4.5:
            raw_score = 12.0
        elif sector_score >= 4.0:
            raw_score = 10.0
        elif sector_score >= 3.5:
            raw_score = 7.0
        elif sector_score >= 3.0:
            raw_score = 4.0
        elif sector_score >= 2.0:
            raw_score = 2.0
        else:
            raw_score = 0.0

        return self.make_result(
            raw_score=raw_score,
            confidence="high",
            reason=f"行业[{sector}]排名第{rank}/{total_sectors}，涨幅{change_pct}%",
            details={
                "sector": sector,
                "sector_rank": rank,
                "sector_change_pct": change_pct,
                "sector_score": round(sector_score, 1),
                "top_sectors": [s["name"] for s in sectors[:5]],
            },
        )

    def get_sector_rotation_signal(self, dt: Optional[date] = None) -> dict:
        """赛道轮动信号（独立调用）"""
        sectors = get_industry_ranking(dt)
        return {
            "top_sectors": [s["name"] for s in sectors[:5]],
            "bottom_sectors": [s["name"] for s in sectors[-5:]],
            "total_sectors": len(sectors),
        }
