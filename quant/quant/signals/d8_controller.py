"""
D8 实控人风险过滤（一票否决维度）

这是一个静态标签 + 动态监控维度：
- 静态：实控人背景（学历/政治/从业经历）→ 人工维护
- 动态：质押比例、减持公告 → 可自动监控

一票否决条件：
- 质押比例 > 50% 且 近1年减持 > 5%
"""

from datetime import date
from typing import Optional, Dict

from .base import Signal, SignalResult


class ControllerRiskSignal(Signal):
    dimension = "d8_controller"
    max_score = 7.0
    description = "实控人风险：治理质量与减持风险"

    def __init__(self):
        # 实控人背景库（人工维护）
        self._controller_db: Dict[str, dict] = {}

    def add_controller(self, code: str, info: dict):
        """添加实控人信息"""
        self._controller_db[code] = info

    def compute(self, code: str, dt: Optional[date] = None) -> SignalResult:
        """
        实控人风险评估

        评分逻辑：
        7分：名校理工+全国人大/政协+从未减持+行业深耕>15年
        5分：学历/政治背景有加分+无治理风险
        3分：背景普通但无明显风险
        1分：有轻微治理风险
        0分：高质押/频繁减持

        一票否决：质押>50% + 近1年减持>5%
        """
        # 获取动态数据（质押+减持）
        risk_data = self._get_risk_data(code, dt)

        # 一票否决检查
        pledge_ratio = risk_data.get("pledge_ratio", 0)
        recent_reduction = risk_data.get("reduction_1y_pct", 0)

        if pledge_ratio > 0.50 and recent_reduction > 0.05:
            return self.make_result(
                raw_score=0.0,
                confidence="high",
                reason=f"一票否决：质押{pledge_ratio*100:.0f}%+减持{recent_reduction*100:.1f}%",
                details=risk_data,
                veto=True,
                veto_reason=f"实控人质押{pledge_ratio*100:.0f}%且近1年减持{recent_reduction*100:.1f}%",
            )

        # 静态背景评分
        controller_info = self._controller_db.get(code)
        if not controller_info:
            # 无背景数据，仅根据动态风险评分
            if pledge_ratio > 0.30 or recent_reduction > 0.03:
                raw_score = 1.0
                reason = "有轻微治理风险"
            else:
                raw_score = 3.0
                reason = "背景数据缺失，无明显风险"
        else:
            raw_score = self._score_background(controller_info)
            reason = self._describe_background(controller_info)

            # 动态风险扣分
            if pledge_ratio > 0.30:
                raw_score = max(0, raw_score - 2)
                reason += "（质押偏高扣分）"
            if recent_reduction > 0.03:
                raw_score = max(0, raw_score - 1)
                reason += "（有减持扣分）"

        return self.make_result(
            raw_score=raw_score,
            confidence="medium" if controller_info else "low",
            reason=reason,
            details={
                **risk_data,
                "has_background_data": controller_info is not None,
            },
        )

    def _get_risk_data(self, code: str, dt: Optional[date] = None) -> dict:
        """
        获取动态风险数据（质押+减持）

        TODO: 接入公告数据/东财数据
        """
        return {
            "pledge_ratio": 0.0,        # 质押比例
            "reduction_1y_pct": 0.0,    # 近1年减持比例
            "increase_1y_pct": 0.0,     # 近1年增持比例
            "last_reduction_date": None,
            "last_increase_date": None,
        }

    def _score_background(self, info: dict) -> float:
        """根据背景信息评分"""
        score = 3.0  # 基础分

        # 学历加分
        edu = info.get("education_level", "")
        if edu in ("985博士", "海外名校博士", "985硕士"):
            score += 1.5
        elif edu in ("211硕士", "985本科"):
            score += 1.0
        elif edu in ("普通本科",):
            score += 0.5

        # 政治背景加分
        political = info.get("political_role", "")
        if "全国" in political:
            score += 1.5
        elif "省级" in political:
            score += 1.0
        elif political:
            score += 0.5

        # 从业年限加分
        years = info.get("industry_years", 0)
        if years >= 15:
            score += 1.0
        elif years >= 10:
            score += 0.5

        return min(7.0, score)

    def _describe_background(self, info: dict) -> str:
        """生成背景描述"""
        parts = []
        if info.get("education_level"):
            parts.append(info["education_level"])
        if info.get("political_role"):
            parts.append(info["political_role"])
        if info.get("industry_years"):
            parts.append(f"从业{info['industry_years']}年")
        return "实控人：" + "，".join(parts) if parts else "实控人背景普通"
