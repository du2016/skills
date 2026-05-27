"""
综合评分引擎

职责：
1. 调用所有维度信号计算
2. 按权重加权合成综合得分
3. 执行一票否决逻辑
4. 输出最终评级
"""

from datetime import date
from typing import Optional, List, Dict
from dataclasses import dataclass, field

from ..config import DIMENSION_WEIGHTS, RATING_THRESHOLDS
from ..signals.base import SignalResult
from ..signals import (
    MacroTimingSignal,
    SectorRotationSignal,
    StockFilterSignal,
    InstitutionalFlowSignal,
    PolicySignal,
    GrowthPotentialSignal,
    MoatSignal,
    ControllerRiskSignal,
    SentimentCycleSignal,
    LeaderIdentificationSignal,
    GlobalSituationSignal,
)


@dataclass
class ScoringResult:
    """综合评分结果"""
    code: str
    total_score: float              # 综合得分 (0-100)
    rating: str                     # 评级 S/A/B/C/D
    dimension_scores: Dict[str, SignalResult] = field(default_factory=dict)
    vetoed: bool = False            # 是否被一票否决
    veto_reasons: List[str] = field(default_factory=list)
    recommendation: str = ""        # 操作建议
    position_range: tuple = (0.0, 0.0)  # 建议仓位范围


class Scorer:
    """综合评分引擎"""

    def __init__(self):
        # 初始化所有信号计算器
        self.signals = {
            "d1_macro": MacroTimingSignal(),
            "d2_sector": SectorRotationSignal(),
            "d3_stock": StockFilterSignal(),
            "d4_flow": InstitutionalFlowSignal(),
            "d5_policy": PolicySignal(),
            "d6_growth": GrowthPotentialSignal(),
            "d7_moat": MoatSignal(),
            "d8_controller": ControllerRiskSignal(),
            "d9_sentiment": SentimentCycleSignal(),
            "d10_leader": LeaderIdentificationSignal(),
            "d11_global": GlobalSituationSignal(),
        }

    def score(self, code: str, dt: Optional[date] = None) -> ScoringResult:
        """
        对单只股票进行十一维综合评分

        流程：
        1. 计算各维度信号
        2. 检查一票否决
        3. 加权合成总分
        4. 确定评级和建议
        """
        # Step 1: 计算所有维度信号
        dimension_scores = {}
        for dim_name, signal in self.signals.items():
            try:
                result = signal.compute(code, dt)
                dimension_scores[dim_name] = result
            except Exception as e:
                # 信号计算失败时给中性分
                dimension_scores[dim_name] = SignalResult(
                    dimension=dim_name,
                    score=0.5,
                    raw_score=signal.max_score * 0.5,
                    max_score=signal.max_score,
                    confidence="low",
                    reason=f"计算异常: {str(e)}",
                )

        # Step 2: 检查一票否决
        veto_reasons = []
        for dim_name, result in dimension_scores.items():
            if result.veto:
                veto_reasons.append(f"[{dim_name}] {result.veto_reason}")

        vetoed = len(veto_reasons) > 0

        # Step 3: 加权合成总分 (0-100)
        total_score = 0.0
        for dim_name, result in dimension_scores.items():
            weight = DIMENSION_WEIGHTS.get(dim_name, 0)
            # score 已归一化到 [0,1]，乘以100得到百分制贡献
            total_score += result.score * weight * 100

        # 被否决的股票得分上限为39（D级）
        if vetoed:
            total_score = min(total_score, 39.0)

        # Step 4: 确定评级
        rating = self._determine_rating(total_score)
        recommendation = self._get_recommendation(rating, vetoed)
        position_range = self._get_position_range(rating)

        return ScoringResult(
            code=code,
            total_score=round(total_score, 1),
            rating=rating,
            dimension_scores=dimension_scores,
            vetoed=vetoed,
            veto_reasons=veto_reasons,
            recommendation=recommendation,
            position_range=position_range,
        )

    def batch_score(
        self, codes: List[str], dt: Optional[date] = None
    ) -> List[ScoringResult]:
        """
        批量评分并排序

        Returns:
            按综合得分从高到低排序的结果列表
        """
        results = []
        for code in codes:
            result = self.score(code, dt)
            results.append(result)

        # 排序：先按是否被否决，再按得分
        results.sort(key=lambda x: (-int(not x.vetoed), -x.total_score))
        return results

    def _determine_rating(self, score: float) -> str:
        """根据得分确定评级"""
        for rating, threshold in sorted(
            RATING_THRESHOLDS.items(),
            key=lambda x: x[1],
            reverse=True,
        ):
            if score >= threshold:
                return rating
        return "D"

    def _get_recommendation(self, rating: str, vetoed: bool) -> str:
        """生成操作建议"""
        if vetoed:
            return "⛔ 一票否决，不可操作"

        recommendations = {
            "S": "🟢 强烈推荐，重仓买入（仓位15-25%）",
            "A": "🟢 推荐买入，标准仓位（仓位10-15%）",
            "B": "🟡 可以关注，轻仓参与（仓位5-10%）",
            "C": "🟠 观察等待，暂不操作",
            "D": "🔴 不推荐，回避",
        }
        return recommendations.get(rating, "")

    def _get_position_range(self, rating: str) -> tuple:
        """获取建议仓位范围"""
        from ..config import POSITION_CONFIG
        return POSITION_CONFIG["default_position"].get(rating, (0.0, 0.0))

    def print_report(self, result: ScoringResult):
        """打印评分报告"""
        print("=" * 60)
        print(f"📋 综合评分报告：{result.code}")
        print("=" * 60)
        print(f"  🎯 综合得分：{result.total_score} / 100")
        print(f"  📊 评级：{result.rating}")
        print(f"  💡 建议：{result.recommendation}")
        print(f"  📈 仓位范围：{result.position_range[0]*100:.0f}%-{result.position_range[1]*100:.0f}%")

        if result.vetoed:
            print(f"\n  ⚠️ 一票否决：")
            for reason in result.veto_reasons:
                print(f"     ❌ {reason}")

        print(f"\n  📊 各维度得分：")
        print(f"  {'维度':<12} {'得分':<10} {'满分':<8} {'置信度':<8} {'理由'}")
        print(f"  {'-'*70}")

        for dim_name, sr in result.dimension_scores.items():
            bar = "█" * int(sr.score * 10) + "░" * (10 - int(sr.score * 10))
            print(
                f"  {dim_name:<12} {sr.raw_score:>5.1f}/{sr.max_score:<4.0f} "
                f"{bar} {sr.confidence:<8} {sr.reason}"
            )

        print("=" * 60)
