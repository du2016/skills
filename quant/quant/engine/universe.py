"""
股票池管理

职责：
1. 维护候选股票池（从各维度筛选出的标的）
2. 定期更新（每周/每月）
3. 支持多种来源：手动添加、基本面筛选、赛道龙头、卡脖子库
"""

from datetime import date
from typing import Optional, List, Set, Dict
from dataclasses import dataclass, field


@dataclass
class StockInfo:
    """股票基本信息"""
    code: str
    name: str
    sector: str = ""           # 所属行业
    market_cap: float = 0.0    # 市值（亿）
    source: str = ""           # 入池来源
    added_date: date = field(default_factory=date.today)
    tags: List[str] = field(default_factory=list)  # 标签：龙头/卡脖子/弹性等


class UniverseManager:
    """股票池管理器"""

    def __init__(self):
        self._universe: Dict[str, StockInfo] = {}
        self._blacklist: Set[str] = set()  # 黑名单（一票否决的）
        self._watchlist: Set[str] = set()  # 观察池

    @property
    def codes(self) -> List[str]:
        """获取当前股票池所有代码"""
        return [c for c in self._universe.keys() if c not in self._blacklist]

    @property
    def size(self) -> int:
        return len(self.codes)

    def add(self, stock: StockInfo):
        """添加股票到池中"""
        self._universe[stock.code] = stock

    def remove(self, code: str):
        """从池中移除"""
        self._universe.pop(code, None)

    def blacklist(self, code: str, reason: str = ""):
        """加入黑名单"""
        self._blacklist.add(code)

    def unblacklist(self, code: str):
        """从黑名单移除"""
        self._blacklist.discard(code)

    def add_to_watchlist(self, code: str):
        """加入观察池"""
        self._watchlist.add(code)

    def get_by_sector(self, sector: str) -> List[str]:
        """按行业筛选"""
        return [
            code for code, info in self._universe.items()
            if info.sector == sector and code not in self._blacklist
        ]

    def get_by_tag(self, tag: str) -> List[str]:
        """按标签筛选"""
        return [
            code for code, info in self._universe.items()
            if tag in info.tags and code not in self._blacklist
        ]

    def load_from_file(self, filepath: str):
        """
        从文件加载股票池

        支持格式：
        - JSON: [{"code": "688XXX", "name": "XX科技", "sector": "电子", ...}]
        - CSV: code,name,sector,market_cap,tags
        """
        import json
        import os

        ext = os.path.splitext(filepath)[1].lower()

        if ext == ".json":
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                self.add(StockInfo(**item))

        elif ext == ".csv":
            import csv
            with open(filepath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    tags = row.get("tags", "").split("|") if row.get("tags") else []
                    self.add(StockInfo(
                        code=row["code"],
                        name=row.get("name", ""),
                        sector=row.get("sector", ""),
                        market_cap=float(row.get("market_cap", 0)),
                        tags=tags,
                    ))

    def save_to_file(self, filepath: str):
        """保存股票池到文件"""
        import json

        data = []
        for code, info in self._universe.items():
            data.append({
                "code": info.code,
                "name": info.name,
                "sector": info.sector,
                "market_cap": info.market_cap,
                "source": info.source,
                "added_date": info.added_date.isoformat(),
                "tags": info.tags,
            })

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def print_summary(self):
        """打印股票池概况"""
        print(f"📊 股票池概况")
        print(f"  总数：{self.size}")
        print(f"  黑名单：{len(self._blacklist)}")
        print(f"  观察池：{len(self._watchlist)}")

        # 按行业统计
        sector_count: Dict[str, int] = {}
        for code in self.codes:
            info = self._universe[code]
            sector_count[info.sector] = sector_count.get(info.sector, 0) + 1

        if sector_count:
            print(f"\n  行业分布：")
            for sector, count in sorted(
                sector_count.items(), key=lambda x: -x[1]
            ):
                print(f"    {sector}: {count}")
