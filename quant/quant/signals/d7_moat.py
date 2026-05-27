"""
D7 卡脖子/护城河信号（标签库模式）

这是一个静态标签维度：
- 维护一个"卡脖子企业库"
- 每只股票标注其壁垒类型和等级
- 定期人工更新（季度级别）

壁垒类型：
- 技术垄断型
- 资源垄断型
- 认证壁垒型
- 生态锁定型
- 工艺积累型
"""

from datetime import date
from typing import Optional, Dict

from .base import Signal, SignalResult


# 壁垒等级定义
MOAT_LEVELS = {
    "S": {"score": 10.0, "desc": "全球唯一/极少数供应商"},
    "A": {"score": 8.0, "desc": "双寡头+认证壁垒"},
    "B": {"score": 5.0, "desc": "工艺积累型，3家以内竞争"},
    "C": {"score": 2.0, "desc": "有一定壁垒但可替代"},
    "N": {"score": 0.0, "desc": "无明显壁垒"},
}


class MoatSignal(Signal):
    dimension = "d7_moat"
    max_score = 10.0
    description = "卡脖子壁垒：识别不可替代的关键环节"

    def __init__(self):
        # 卡脖子企业库
        # key: 股票代码, value: 壁垒信息
        self._moat_db: Dict[str, dict] = {}
        self._load_default_db()

    def _load_default_db(self):
        """
        加载默认卡脖子企业库

        格式：
        {
            "code": {
                "level": "S/A/B/C/N",
                "type": "技术垄断/资源垄断/认证壁垒/生态锁定/工艺积累",
                "irreplaceability": "描述",
                "downstream_dependency": "high/medium/low",
                "domestic_substitution": "唯一/双寡头/三家竞争/多家竞争",
                "pricing_power": "极强/强/中/弱",
            }
        }

        TODO: 从外部文件加载，支持定期更新
        """
        # 示例数据（实际使用时从JSON/CSV加载）
        self._moat_db = {
            # 示例：某光刻胶企业
            # "688XXX": {
            #     "level": "A",
            #     "type": "工艺积累",
            #     "irreplaceability": "国内唯一通过XX认证",
            #     "downstream_dependency": "high",
            #     "domestic_substitution": "双寡头",
            #     "pricing_power": "强",
            # },
        }

    def add_stock(self, code: str, moat_info: dict):
        """添加/更新卡脖子标签"""
        self._moat_db[code] = moat_info

    def load_from_file(self, filepath: str):
        """从JSON文件加载企业库"""
        import json
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._moat_db.update(data)

    def compute(self, code: str, dt: Optional[date] = None) -> SignalResult:
        """
        查询个股的卡脖子等级

        如果不在库中，默认为N级（无明显壁垒）
        """
        moat_info = self._moat_db.get(code)

        if not moat_info:
            return self.make_result(
                raw_score=0.0,
                confidence="low",
                reason="未收录在卡脖子企业库中",
                details={"in_database": False},
            )

        level = moat_info.get("level", "N")
        level_info = MOAT_LEVELS.get(level, MOAT_LEVELS["N"])

        return self.make_result(
            raw_score=level_info["score"],
            confidence="high",
            reason=f"{level}级壁垒（{moat_info.get('type', '未知')}）：{level_info['desc']}",
            details={
                "in_database": True,
                "level": level,
                "type": moat_info.get("type"),
                "irreplaceability": moat_info.get("irreplaceability"),
                "downstream_dependency": moat_info.get("downstream_dependency"),
                "domestic_substitution": moat_info.get("domestic_substitution"),
                "pricing_power": moat_info.get("pricing_power"),
            },
        )
