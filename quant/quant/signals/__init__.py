from .base import Signal, SignalResult
from .d1_macro import MacroTimingSignal
from .d2_sector import SectorRotationSignal
from .d3_stock import StockFilterSignal
from .d4_flow import InstitutionalFlowSignal
from .d5_policy import PolicySignal
from .d6_growth import GrowthPotentialSignal
from .d7_moat import MoatSignal
from .d8_controller import ControllerRiskSignal
from .d9_sentiment import SentimentCycleSignal
from .d10_leader import LeaderIdentificationSignal
from .d11_global import GlobalSituationSignal

ALL_SIGNALS = [
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
]
