"""
D5 政策动向信号（半自动）

这是一个半自动维度：
- 政策事件需要人工录入或NLP解析
- 系统维护一个"政策事件表"，记录政策方向和受益行业
- 个股通过行业映射获得政策得分

数据结构：
    PolicyEvent:
        - name: 政策名称
        - date: 发布日期
        - department: 发布部门
        - strength: 力度 (1-5)
        - sectors: 受益行业列表
        - duration: 持续性 (short/medium/long)
        - certainty: 落地确定性 (high/medium/low)
"""

from datetime import date
from typing import Optional, List
from dataclasses import dataclass, field

from .base import Signal, SignalResult


@dataclass
class PolicyEvent:
    """政策事件"""
    name: str
    event_date: date
    department: str
    strength: int  # 1-5
    sectors: List[str] = field(default_factory=list)
    duration: str = "medium"  # short / medium / long
    certainty: str = "medium"  # high / medium / low
    is_negative: bool = False  # 是否为负面政策（收紧/打压）


class PolicySignal(Signal):
    dimension = "d5_policy"
    max_score = 10.0
    description = "政策动向：识别政策催化与风险"

    def __init__(self):
        # 政策事件库（人工维护或NLP自动更新）
        self._policy_events: List[PolicyEvent] = []

    def add_event(self, event: PolicyEvent):
        """添加政策事件"""
        self._policy_events.append(event)

    def load_events(self, events: List[dict]):
        """批量加载政策事件"""
        for e in events:
            self._policy_events.append(PolicyEvent(**e))

    def compute(self, code: str, dt: Optional[date] = None) -> SignalResult:
        """
        计算个股的政策受益度

        逻辑：
        1. 确定个股所属行业
        2. 查找近期（90天内）影响该行业的政策事件
        3. 综合政策力度、持续性、确定性计算得分
        """
        target_date = dt or date.today()
        sector = self._get_stock_sector(code)

        # 查找相关政策
        relevant_policies = self._find_relevant_policies(sector, target_date)

        if not relevant_policies:
            return self.make_result(
                raw_score=2.0,  # 政策中性
                confidence="low",
                reason="近期无明确相关政策",
                details={"sector": sector, "policies": []},
            )

        # 计算综合政策得分
        policy_score = self._calculate_policy_score(relevant_policies)

        # 检查是否有负面政策（扣分项）
        negative = [p for p in relevant_policies if p.is_negative]
        if negative:
            policy_score = max(0, policy_score - 5)

        raw_score = min(10.0, policy_score)

        return self.make_result(
            raw_score=raw_score,
            confidence="high" if relevant_policies else "low",
            reason=f"相关政策{len(relevant_policies)}条，综合力度{raw_score:.1f}/10",
            details={
                "sector": sector,
                "policies": [p.name for p in relevant_policies],
                "negative_policies": [p.name for p in negative],
            },
        )

    def _get_stock_sector(self, code: str) -> str:
        """获取股票所属行业"""
        # TODO: 接入行业分类
        return "未知"

    def _find_relevant_policies(
        self, sector: str, target_date: date, lookback_days: int = 90
    ) -> List[PolicyEvent]:
        """查找近期影响该行业的政策"""
        from datetime import timedelta

        cutoff = target_date - timedelta(days=lookback_days)
        return [
            p for p in self._policy_events
            if p.event_date >= cutoff and sector in p.sectors
        ]

    def _calculate_policy_score(self, policies: List[PolicyEvent]) -> float:
        """
        综合政策得分

        单条政策得分 = strength × duration_weight × certainty_weight
        取最高的一条政策得分（不叠加，避免重复计算）
        """
        duration_weight = {"short": 0.6, "medium": 0.8, "long": 1.0}
        certainty_weight = {"low": 0.5, "medium": 0.7, "high": 1.0}

        scores = []
        for p in policies:
            if p.is_negative:
                continue
            score = (
                p.strength * 2  # strength 1-5 → 2-10
                * duration_weight.get(p.duration, 0.8)
                * certainty_weight.get(p.certainty, 0.7)
            )
            scores.append(score)

        return max(scores) if scores else 2.0
