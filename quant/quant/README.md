# 十一维量化交易系统 (11D Quantitative Trading System)

基于十一维选股模型的实时量化交易框架，数据源为聚宽 jqdatasdk。

## 安装

```bash
pip install jqdatasdk
```

## 配置

设置聚宽账号（在 https://www.joinquant.com 免费注册）：

```bash
export JQ_USER='你的手机号'
export JQ_PASS='你的密码'
```

## 运行

```bash
cd stock-selection

# 单票评分
python run_quant.py --mode score --codes 603290

# 多票对比
python run_quant.py --mode score --codes 603290 688017 300750 600519

# 每日策略（需要先准备股票池 output/universe.json）
python run_quant.py --mode daily

# 回测
python run_quant.py --mode backtest --start 2024-01-01 --end 2024-12-31
```

## 架构

```
quant/
├── config.py              # 全局配置（权重、阈值、参数）
├── signals/               # 信号层：各维度信号计算
│   ├── base.py            # 信号基类
│   ├── d1_macro.py        # D1 宏观择时（指数PE分位）
│   ├── d2_sector.py       # D2 赛道轮动（行业指数排名）
│   ├── d3_stock.py        # D3 基本面筛选（ROE/负债率/增速/PE/市值）
│   ├── d4_flow.py         # D4 主力资金流（资金流+融资+龙虎榜）
│   ├── d5_policy.py       # D5 政策事件（半自动，人工录入）
│   ├── d6_growth.py       # D6 成长潜力（营收/利润增速）
│   ├── d7_moat.py         # D7 卡脖子标签库（人工维护）
│   ├── d8_controller.py   # D8 实控人风险（人工+解禁数据）
│   ├── d9_sentiment.py    # D9 情绪周期（涨停/跌停/涨跌比）
│   ├── d10_leader.py      # D10 龙头辨识（市场结构健康度）
│   └── d11_global.py      # D11 国际形势（半自动）
├── engine/                # 决策层
│   ├── scorer.py          # 综合评分引擎（加权+一票否决）
│   ├── position.py        # 仓位管理
│   ├── risk.py            # 风控规则（8条铁律）
│   └── universe.py        # 股票池管理
├── execution/             # 执行层
│   └── trader.py          # 交易执行器（模拟/实盘）
├── backtest/              # 回测框架
│   └── engine.py          # 回测引擎
├── data/                  # 数据接口
│   └── provider.py        # 聚宽数据源适配器
└── main.py                # 主入口
```

## 数据源（聚宽 jqdatasdk）

| 数据               | 聚宽API                           | 用于维度 |
| ------------------ | --------------------------------- | -------- |
| 行情/K线           | `get_price()`                     | D1/D2/D3 |
| 估值(PE/PB/市值)   | `valuation` 表                    | D3/D6    |
| 财务指标(ROE/增速) | `indicator` 表                    | D3/D6    |
| 资产负债表         | `balance` 表                      | D3       |
| 现金流量表         | `cash_flow` 表                    | D3       |
| 行业分类(申万)     | `get_industry()`                  | D2       |
| 概念板块           | `get_concept()`                   | D10      |
| 资金流             | `get_money_flow()`                | D4       |
| 融资融券           | `get_mtss()`                      | D4       |
| 龙虎榜             | `get_billboard_list()`            | D4       |
| 限售解禁           | `get_locked_shares()`             | D8       |
| 涨跌停             | `get_price(high_limit/low_limit)` | D9/D10   |
| 指数PE分位         | `get_price()` 历史                | D1       |

## 免费额度

聚宽免费用户每天100万条数据，足够：
- 单票评分：约50条查询
- 每日策略（50只股票池）：约2500条
- 市场情绪扫描（全市场涨跌停）：约10000条

## 设计原则

1. **单一数据源**：全部走聚宽，不拼接多个免费接口，数据一致性有保障
2. **信号标准化**：所有维度输出归一化到 [0, 1]
3. **铁律不可违**：8条交易纪律硬编码，任何信号无法覆盖
4. **尾盘决策**：默认14:30后生成交易信号
5. **可回测**：所有信号函数接受日期参数，支持历史回放
