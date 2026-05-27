"""
D10 龙头辨识与板块结构信号

量化指标：
- 连板天数（板块内最高）
- 启动时间（板块内最早涨停）
- 换手率区间（5%-15%为健康）
- 板块涨停股集中度
- 龙头带动效应（龙头涨时板块跟涨比例）

板块结构类型：
- 一超多强（最佳）
- 双龙争霸（需选边）
- 群龙无首（回避）
- 板块割裂（一票否决降仓）
"""

from datetime import date
from typing import Optional, List, Dict

from .base import Signal, SignalResult
from ..config import LEADER_CONFIG
from ..data.provider import get_stock_industry, get_market_sentiment


class LeaderIdentificationSignal(Signal):
    dimension = "d10_leader"
    max_score = 5.0
    description = "龙头辨识：判断板块结构和龙头地位"

    def compute(self, code: str, dt: Optional[date] = None) -> SignalResult:
        """
        判断个股是否为龙头 + 板块结构是否健康

        评分：
        5分：绝对龙头 + 一超多强
        4分：板块龙头 + 结构健康
        2分：非龙头但板块结构健康
        1分：板块轻度割裂
        0分：板块严重割裂/群龙无首
        """
        # 获取个股所在板块的结构数据
        sector = self._get_stock_sector(code)
        structure = self._analyze_sector_structure(sector, dt)
        is_leader = self._check_if_leader(code, sector, dt)

        # 评分
        structure_type = structure.get("type", "unknown")

        if is_leader and structure_type == "one_dominant":
            raw_score = 5.0
            reason = f"绝对龙头+一超多强结构"
        elif is_leader and structure_type in ("healthy", "dual_leaders"):
            raw_score = 4.0
            reason = f"板块龙头+结构健康"
        elif not is_leader and structure_type in ("one_dominant", "healthy"):
            raw_score = 2.0
            reason = f"非龙头但板块结构健康"
        elif structure_type == "mild_split":
            raw_score = 1.0
            reason = "板块轻度割裂"
        else:
            raw_score = 0.0
            reason = "板块严重割裂或群龙无首"

        # 一票否决：严重割裂
        veto = structure_type == "severe_split"

        return self.make_result(
            raw_score=raw_score,
            confidence="medium",
            reason=reason,
            details={
                "sector": sector,
                "is_leader": is_leader,
                "structure_type": structure_type,
                "structure": structure,
            },
            veto=veto,
            veto_reason="板块严重割裂，铁律4：降仓至半仓以下" if veto else "",
        )

    def _get_stock_sector(self, code: str) -> str:
        """获取股票所属行业"""
        try:
            info = get_stock_industry(code)
            return info.get("sw_l1", "")
        except Exception:
            return ""

    def _check_if_leader(self, code: str, sector: str, dt: Optional[date] = None) -> bool:
        """判断是否为板块龙头 — 简化：暂不判定"""
        return False

    def _analyze_sector_structure(self, sector: str, dt: Optional[date] = None) -> dict:
        """
        分析板块结构 — 基于涨跌比判断市场健康度
        """
        try:
            sentiment = get_market_sentiment(dt)
            limit_up = sentiment.get("limit_up_count", 0)
            limit_down = sentiment.get("limit_down_count", 0)
            advance = sentiment.get("advance_count", 0)
            decline = sentiment.get("decline_count", 0)

            # 判断结构类型
            if limit_up >= 80 and advance > decline * 2:
                structure_type = "one_dominant"
            elif limit_up >= 50 and advance > decline * 1.5:
                structure_type = "healthy"
            elif limit_up >= 30 and advance > decline:
                structure_type = "dual_leaders"
            elif limit_up < 15 and limit_down > limit_up * 2:
                structure_type = "severe_split"
            elif decline > advance * 1.5:
                structure_type = "mild_split"
            else:
                structure_type = "healthy"

            return {
                "type": structure_type,
                "limit_up": limit_up,
                "limit_down": limit_down,
                "advance": advance,
                "decline": decline,
            }
        except Exception:
            return {"type": "healthy"}

    def get_market_split_degree(self, dt: Optional[date] = None) -> dict:
        """计算全市场板块割裂度"""
        structure = self._analyze_sector_structure("", dt)
        split_degree = 0.0
        stype = structure.get("type", "healthy")

        degree_map = {
            "severe_split": 0.9,
            "mild_split": 0.6,
            "dual_leaders": 0.4,
            "healthy": 0.2,
            "one_dominant": 0.1,
        }
        split_degree = degree_map.get(stype, 0.3)

        return {
            "split_degree": split_degree,
            "structure_type": stype,
            "details": structure,
        }
