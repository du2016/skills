"""
信号基类：所有维度信号的统一接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class SignalResult:
    """信号计算结果"""
    dimension: str              # 维度名称 (d1_macro, d2_sector, ...)
    score: float                # 归一化得分 [0, 1]
    raw_score: float            # 原始得分（维度满分制）
    max_score: float            # 该维度满分
    confidence: str             # 置信度: high / medium / low
    reason: str                 # 得分理由（一句话）
    details: dict = field(default_factory=dict)  # 详细数据
    veto: bool = False          # 是否触发一票否决
    veto_reason: str = ""       # 否决原因
    timestamp: Optional[str] = None  # 数据时间戳


class Signal(ABC):
    """信号基类"""

    # 子类必须定义
    dimension: str = ""
    max_score: float = 0.0
    description: str = ""

    @abstractmethod
    def compute(self, code: str, dt: Optional[date] = None) -> SignalResult:
        """
        计算信号得分

        Args:
            code: 股票代码（6位）
            dt: 计算日期，None表示当天（实时）

        Returns:
            SignalResult: 标准化的信号结果
        """
        pass

    def normalize(self, raw_score: float) -> float:
        """将原始得分归一化到 [0, 1]"""
        if self.max_score <= 0:
            return 0.0
        return max(0.0, min(1.0, raw_score / self.max_score))

    def make_result(
        self,
        raw_score: float,
        confidence: str = "medium",
        reason: str = "",
        details: dict = None,
        veto: bool = False,
        veto_reason: str = "",
        timestamp: str = None,
    ) -> SignalResult:
        """便捷方法：构造标准结果"""
        return SignalResult(
            dimension=self.dimension,
            score=self.normalize(raw_score),
            raw_score=raw_score,
            max_score=self.max_score,
            confidence=confidence,
            reason=reason,
            details=details or {},
            veto=veto,
            veto_reason=veto_reason,
            timestamp=timestamp,
        )


class MarketWideSignal(Signal):
    """
    市场级信号基类（D1/D9/D11等不针对个股的信号）
    compute 的 code 参数可忽略
    """

    def compute(self, code: str = "", dt: Optional[date] = None) -> SignalResult:
        return self.compute_market(dt)

    @abstractmethod
    def compute_market(self, dt: Optional[date] = None) -> SignalResult:
        pass


class SectorSignal(Signal):
    """
    板块级信号基类（D2/D10等针对板块的信号）
    """

    @abstractmethod
    def compute_sector(self, sector: str, dt: Optional[date] = None) -> SignalResult:
        """计算板块级信号"""
        pass
