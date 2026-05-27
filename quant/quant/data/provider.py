"""
数据源适配器 — 基于聚宽 jqdatasdk

聚宽提供完整的A股数据，包括：
- 行情数据：日/分钟K线、实时行情
- 财务数据：三表+衍生指标（ROE/毛利率/负债率等）
- 估值数据：PE/PB/PS/PCF/市值
- 行业分类：申万一级/二级/三级
- 概念板块：概念成分股
- 融资融券：日级明细
- 限售解禁：解禁日历
- 龙虎榜：上榜记录+席位
- 指数数据：行业指数/宽基指数

依赖：pip install jqdatasdk
注册：https://www.joinquant.com （免费用户每天100万条额度）

使用前需要认证：
    import jqdatasdk as jq
    jq.auth('手机号', '密码')
"""

import os
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict

import jqdatasdk as jq
from jqdatasdk import (
    auth, get_price, get_fundamentals, get_industry,
    get_concept, get_mtss, get_money_flow,
    get_locked_shares, get_billboard_list,
    query, valuation, income, balance, cash_flow, indicator,
    get_all_securities, get_security_info, get_index_stocks,
    get_trade_days, normalize_code,
)

# 认证（从环境变量读取）
_JQ_USER = os.environ.get("JQ_USER", "")
_JQ_PASS = os.environ.get("JQ_PASS", "")
_authenticated = False


def _ensure_auth():
    """确保已认证"""
    global _authenticated
    if _authenticated:
        return
    user = _JQ_USER
    pwd = _JQ_PASS
    if not user or not pwd:
        raise RuntimeError(
            "聚宽未认证。请设置环境变量：\n"
            "  export JQ_USER='你的手机号'\n"
            "  export JQ_PASS='你的密码'\n"
            "或在代码中调用 jq.auth('手机号', '密码')"
        )
    auth(user, pwd)
    _authenticated = True


def _to_jq_code(code: str) -> str:
    """6位代码转聚宽格式：603290 → 603290.XSHG"""
    if "." in code:
        return code
    if code.startswith(("6", "9")):
        return f"{code}.XSHG"
    elif code.startswith("8") or code.startswith("4"):
        return f"{code}.XBJE"
    else:
        return f"{code}.XSHE"


def _from_jq_code(jq_code: str) -> str:
    """聚宽格式转6位代码：603290.XSHG → 603290"""
    return jq_code.split(".")[0]


def _last_trade_day(dt: Optional[date] = None) -> date:
    """获取最近的交易日（确保在账号数据范围内）"""
    _ensure_auth()
    target = dt or date.today()
    try:
        days = get_trade_days(end_date=target, count=1)
        if len(days) > 0:
            return days[0]
    except Exception:
        pass
    return target


# ================================================================
# 1. 行情数据
# ================================================================

def get_realtime_quote(code: str) -> dict:
    """获取最新行情（收盘价/涨跌幅/成交量/换手率等）"""
    _ensure_auth()
    jq_code = _to_jq_code(code)
    dt = _last_trade_day()
    df = get_price(jq_code, end_date=dt, count=1, fields=[
        'open', 'close', 'high', 'low', 'volume', 'money'
    ])
    if df.empty:
        return {}

    row = df.iloc[-1]
    # 获取估值数据
    val = get_fundamentals(query(
        valuation.code,
        valuation.pe_ratio,
        valuation.pb_ratio,
        valuation.ps_ratio,
        valuation.market_cap,
        valuation.circulating_market_cap,
        valuation.turnover_ratio,
    ).filter(valuation.code == jq_code), date=dt)

    result = {
        "code": code,
        "price": float(row["close"]),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "volume": int(row["volume"]),
        "amount": float(row["money"]),
    }

    if not val.empty:
        v = val.iloc[0]
        result.update({
            "pe_ttm": float(v["pe_ratio"]) if v["pe_ratio"] else 0,
            "pb": float(v["pb_ratio"]) if v["pb_ratio"] else 0,
            "ps": float(v["ps_ratio"]) if v["ps_ratio"] else 0,
            "market_cap_yi": float(v["market_cap"]) if v["market_cap"] else 0,
            "float_cap_yi": float(v["circulating_market_cap"]) if v["circulating_market_cap"] else 0,
            "turnover_pct": float(v["turnover_ratio"]) if v["turnover_ratio"] else 0,
        })

    return result


def get_batch_quotes(codes: List[str]) -> Dict[str, dict]:
    """批量获取行情"""
    result = {}
    for code in codes:
        try:
            result[code] = get_realtime_quote(code)
        except Exception:
            continue
    return result


def get_klines(code: str, count: int = 120, frequency: str = "daily") -> List[dict]:
    """
    获取K线数据
    frequency: daily / minute / 5m / 15m / 30m / 60m / weekly / monthly
    """
    _ensure_auth()
    jq_code = _to_jq_code(code)
    dt = _last_trade_day()
    df = get_price(jq_code, end_date=dt, count=count, frequency=frequency,
                   fields=['open', 'close', 'high', 'low', 'volume', 'money'])
    if df.empty:
        return []

    records = []
    for idx, row in df.iterrows():
        records.append({
            "date": str(idx)[:10],
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row["volume"]),
            "amount": float(row["money"]),
        })
    return records


# ================================================================
# 2. 财务数据 + 估值
# ================================================================

def get_financials_data(code: str, dt: Optional[date] = None) -> dict:
    """
    获取财务+估值综合数据
    返回: ROE/毛利率/净利率/营收增速/净利增速/负债率/现金流/PE/PB/市值等
    """
    _ensure_auth()
    jq_code = _to_jq_code(code)
    target_date = dt or _last_trade_day()

    # 估值数据
    val_df = get_fundamentals(query(
        valuation.code,
        valuation.pe_ratio,
        valuation.pb_ratio,
        valuation.ps_ratio,
        valuation.pcf_ratio,
        valuation.market_cap,
        valuation.circulating_market_cap,
        valuation.turnover_ratio,
    ).filter(valuation.code == jq_code), date=target_date)

    # 核心财务指标
    ind_df = get_fundamentals(query(
        indicator.code,
        indicator.roe,
        indicator.roa,
        indicator.gross_profit_margin,
        indicator.net_profit_margin,
        indicator.inc_revenue_year_on_year,
        indicator.inc_net_profit_year_on_year,
        indicator.inc_revenue_annual,
        indicator.inc_net_profit_annual,
        indicator.eps,
        indicator.operating_profit,
    ).filter(indicator.code == jq_code), date=target_date)

    # 资产负债率
    bal_df = get_fundamentals(query(
        balance.code,
        balance.total_liability,
        balance.total_assets,
    ).filter(balance.code == jq_code), date=target_date)

    # 经营性现金流
    cf_df = get_fundamentals(query(
        cash_flow.code,
        cash_flow.net_operate_cash_flow,
    ).filter(cash_flow.code == jq_code), date=target_date)

    result = {"code": code}

    if not val_df.empty:
        v = val_df.iloc[0]
        result.update({
            "pe_ttm": float(v["pe_ratio"] or 0),
            "pb": float(v["pb_ratio"] or 0),
            "ps": float(v["ps_ratio"] or 0),
            "pcf": float(v["pcf_ratio"] or 0),
            "market_cap_yi": float(v["market_cap"] or 0),
            "float_cap_yi": float(v["circulating_market_cap"] or 0),
            "turnover_pct": float(v["turnover_ratio"] or 0),
        })

    if not ind_df.empty:
        i = ind_df.iloc[0]
        result.update({
            "roe": float(i["roe"] or 0) / 100,  # 转为小数
            "roa": float(i["roa"] or 0) / 100,
            "gross_margin": float(i["gross_profit_margin"] or 0) / 100,
            "net_margin": float(i["net_profit_margin"] or 0) / 100,
            "revenue_growth_yoy": float(i["inc_revenue_year_on_year"] or 0) / 100,
            "profit_growth_yoy": float(i["inc_net_profit_year_on_year"] or 0) / 100,
            "eps": float(i["eps"] or 0),
        })

    if not bal_df.empty:
        b = bal_df.iloc[0]
        total_assets = float(b["total_assets"] or 1)
        total_liability = float(b["total_liability"] or 0)
        result["debt_ratio"] = total_liability / total_assets if total_assets > 0 else 0

    if not cf_df.empty:
        c = cf_df.iloc[0]
        result["operating_cashflow"] = float(c["net_operate_cash_flow"] or 0)

    return result


# ================================================================
# 3. 行业分类 + 概念板块
# ================================================================

def get_stock_industry(code: str, dt: Optional[date] = None) -> dict:
    """
    获取股票所属行业（申万一级/二级）
    返回: {sw_l1: "电子", sw_l2: "半导体", sw_l3: "..."}
    """
    _ensure_auth()
    jq_code = _to_jq_code(code)
    target_date = dt or _last_trade_day()
    ind = get_industry(jq_code, date=target_date)

    result = {"sw_l1": "", "sw_l2": "", "sw_l3": ""}
    if jq_code in ind:
        info = ind[jq_code]
        if "sw_l1" in info:
            result["sw_l1"] = info["sw_l1"].get("industry_name", "")
        if "sw_l2" in info:
            result["sw_l2"] = info["sw_l2"].get("industry_name", "")
        if "sw_l3" in info:
            result["sw_l3"] = info["sw_l3"].get("industry_name", "")
    return result


def get_stock_concepts(code: str, dt: Optional[date] = None) -> List[str]:
    """获取股票所属概念板块列表"""
    _ensure_auth()
    jq_code = _to_jq_code(code)
    target_date = dt or _last_trade_day()
    concepts = get_concept(jq_code, date=target_date)
    if jq_code in concepts:
        return [c["concept_name"] for c in concepts[jq_code].values()]
    return []


def get_industry_stocks_list(industry_code: str, dt: Optional[date] = None) -> List[str]:
    """获取行业成分股列表"""
    _ensure_auth()
    target_date = dt or _last_trade_day()
    stocks = get_industry_stocks(industry_code, date=target_date)
    return [_from_jq_code(s) for s in stocks]


# ================================================================
# 4. 行业排名（通过行业指数涨跌幅计算）
# ================================================================

def get_industry_ranking(dt: Optional[date] = None) -> List[dict]:
    """
    获取申万一级行业涨跌排名
    返回: [{name, code, change_pct, rank}]
    """
    _ensure_auth()
    target_date = dt or _last_trade_day()
    days = get_trade_days(end_date=target_date, count=2)
    if len(days) < 2:
        return []
    prev_date = days[0]

    # 获取所有申万一级行业
    industries = jq.get_industries(name='sw_l1')

    results = []
    for idx, row in industries.iterrows():
        ind_code = idx
        ind_name = row["name"]

        try:
            # 用行业成分股的均值涨跌近似行业涨跌
            # 直接获取两天的行业指数收盘价
            df = get_price(
                ind_code,
                start_date=prev_date, end_date=target_date,
                fields=['close'], panel=False
            )
            if df is not None and len(df) >= 2:
                change_pct = (float(df.iloc[-1]["close"]) / float(df.iloc[0]["close"]) - 1) * 100
            else:
                change_pct = 0
        except Exception:
            change_pct = 0

        results.append({
            "name": ind_name,
            "code": ind_code,
            "change_pct": round(change_pct, 2),
        })

    results.sort(key=lambda x: x["change_pct"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    return results


# ================================================================
# 5. 资金流 + 融资融券
# ================================================================

def get_money_flow_data(code: str, days: int = 20) -> List[dict]:
    """
    获取个股资金流（主力/散户净流入）
    返回: [{date, net_amount_main, net_amount_xl, net_amount_l, ...}]
    """
    _ensure_auth()
    jq_code = _to_jq_code(code)
    target_date = _last_trade_day()
    start_date = target_date - timedelta(days=days * 2)

    df = get_money_flow([jq_code], start_date=start_date, end_date=target_date)
    if df.empty:
        return []

    records = []
    for _, row in df.iterrows():
        records.append({
            "date": str(row.get("date", ""))[:10],
            "net_amount_main": float(row.get("net_amount_main", 0) or 0),
            "net_amount_xl": float(row.get("net_amount_xl", 0) or 0),
            "net_amount_l": float(row.get("net_amount_l", 0) or 0),
            "net_amount_m": float(row.get("net_amount_m", 0) or 0),
            "net_amount_s": float(row.get("net_amount_s", 0) or 0),
        })
    return records[-days:]


def get_margin_data(code: str, days: int = 20) -> List[dict]:
    """
    获取融资融券数据
    返回: [{date, rzye(融资余额), rzmre(融资买入), rqye(融券余额)}]
    """
    _ensure_auth()
    jq_code = _to_jq_code(code)
    target_date = _last_trade_day()
    start_date = target_date - timedelta(days=days * 2)

    df = get_mtss(jq_code, start_date=start_date, end_date=target_date)
    if df.empty:
        return []

    records = []
    for _, row in df.iterrows():
        records.append({
            "date": str(row.get("date", ""))[:10],
            "rzye": float(row.get("fin_value", 0) or 0),
            "rzmre": float(row.get("fin_buy_value", 0) or 0),
            "rqye": float(row.get("sec_value", 0) or 0),
            "rqmcl": float(row.get("sec_sell_volume", 0) or 0),
        })
    return records[-days:]


# ================================================================
# 6. 龙虎榜
# ================================================================

def get_billboard_data(code: str, dt: Optional[date] = None, lookback: int = 30) -> List[dict]:
    """
    获取龙虎榜数据
    返回: [{date, reason, buy_value, sell_value, net_value, ...}]
    """
    _ensure_auth()
    jq_code = _to_jq_code(code)
    target_date = dt or _last_trade_day()
    start_date = target_date - timedelta(days=lookback)

    df = get_billboard_list(stock_list=[jq_code],
                            start_date=start_date, end_date=target_date)
    if df is None or df.empty:
        return []

    records = []
    for _, row in df.iterrows():
        records.append({
            "date": str(row.get("day", ""))[:10],
            "code": _from_jq_code(str(row.get("stock_code", ""))),
            "reason": row.get("abnormal_name", ""),
            "buy_value": float(row.get("total_buy_amount", 0) or 0),
            "sell_value": float(row.get("total_sell_amount", 0) or 0),
            "net_value": float(row.get("total_buy_amount", 0) or 0) - float(row.get("total_sell_amount", 0) or 0),
        })
    return records


# ================================================================
# 7. 解禁 + 股东
# ================================================================

def get_lockup_data(code: str, forward_days: int = 90) -> dict:
    """获取限售解禁日历"""
    _ensure_auth()
    jq_code = _to_jq_code(code)
    target_date = _last_trade_day()
    end_date = target_date + timedelta(days=forward_days)

    df = get_locked_shares(stock_list=[jq_code],
                           start_date=target_date, forward_count=forward_days)
    if df is None or df.empty:
        return {"upcoming": []}

    records = []
    for _, row in df.iterrows():
        records.append({
            "date": str(row.get("day", ""))[:10],
            "shares": float(row.get("num", 0) or 0),
            "rate": float(row.get("rate1", 0) or 0),
        })
    return {"upcoming": records}


# ================================================================
# 8. 涨停/跌停统计（用于情绪周期判定）
# ================================================================

def get_limit_up_stocks(dt: Optional[date] = None) -> List[dict]:
    """
    获取涨停股列表（采样方式，节省额度）
    """
    _ensure_auth()
    target_date = dt or _last_trade_day()

    try:
        hs300 = get_index_stocks("000300.XSHG", date=target_date)
        zz500 = get_index_stocks("000905.XSHG", date=target_date)
        zz1000 = get_index_stocks("000852.XSHG", date=target_date)
        sample_codes = list(set(hs300 + zz500 + zz1000))
    except Exception:
        return []

    limit_up_list = []
    try:
        df = get_price(sample_codes, end_date=target_date, count=1,
                       fields=['close', 'high_limit'], panel=False)
        if df.empty:
            return []

        for _, row in df.iterrows():
            if row["close"] >= row["high_limit"] * 0.998:
                limit_up_list.append({
                    "code": _from_jq_code(row["code"]),
                    "close": float(row["close"]),
                })
    except Exception:
        pass

    return limit_up_list


def get_market_sentiment(dt: Optional[date] = None) -> dict:
    """
    获取市场情绪数据（涨停数/跌停数/涨跌比）
    使用沪深300+中证500成分股采样，节省数据额度
    """
    _ensure_auth()
    target_date = dt or _last_trade_day()

    # 用沪深300+中证500采样（约800只），而非全市场5000只
    try:
        hs300 = get_index_stocks("000300.XSHG", date=target_date)
        zz500 = get_index_stocks("000905.XSHG", date=target_date)
        sample_codes = list(set(hs300 + zz500))
    except Exception:
        return {"limit_up_count": 0, "limit_down_count": 0,
                "advance_count": 0, "decline_count": 0}

    limit_up = 0
    limit_down = 0
    advance = 0
    decline = 0

    try:
        df = get_price(sample_codes, end_date=target_date, count=1,
                       fields=['close', 'high_limit', 'low_limit', 'pre_close'],
                       panel=False)
        if df.empty:
            return {"limit_up_count": 0, "limit_down_count": 0,
                    "advance_count": 0, "decline_count": 0}

        for _, row in df.iterrows():
            close = row["close"]
            pre_close = row["pre_close"]
            high_limit = row["high_limit"]
            low_limit = row["low_limit"]

            if close >= high_limit * 0.998:
                limit_up += 1
            elif close <= low_limit * 1.002:
                limit_down += 1

            if close > pre_close:
                advance += 1
            elif close < pre_close:
                decline += 1
    except Exception:
        pass

    # 按采样比例放大到全市场估算（约5000只/800只≈6倍）
    scale = 6
    return {
        "date": str(target_date),
        "limit_up_count": limit_up * scale,
        "limit_down_count": limit_down * scale,
        "advance_count": advance,
        "decline_count": decline,
        "sample_size": len(sample_codes),
    }


# ================================================================
# 9. 指数数据
# ================================================================

def get_index_quote(index_code: str, dt: Optional[date] = None) -> dict:
    """
    获取指数行情
    常用指数：000001.XSHG(上证), 000300.XSHG(沪深300), 399006.XSHE(创业板指)
    """
    _ensure_auth()
    target_date = dt or _last_trade_day()
    df = get_price(index_code, end_date=target_date, count=1,
                   fields=['open', 'close', 'high', 'low', 'volume', 'money'])
    if df.empty:
        return {}
    row = df.iloc[-1]
    return {
        "code": index_code,
        "close": float(row["close"]),
        "volume": int(row["volume"]),
        "amount": float(row["money"]),
    }


def get_index_pe_percentile(index_code: str = "000300.XSHG", years: int = 5) -> dict:
    """
    计算指数PE历史分位数
    用于D1宏观择时
    注意：免费账号数据范围有限，自动适配
    """
    _ensure_auth()
    target_date = _last_trade_day()
    # 免费账号约1年数据，取可用范围
    start_date = target_date - timedelta(days=min(years * 365, 300))

    try:
        df = get_price(index_code, start_date=start_date, end_date=target_date,
                       frequency="daily", fields=["close"])
    except Exception:
        return {"percentile": 0.5}

    if df.empty or len(df) < 10:
        return {"percentile": 0.5}

    current = df.iloc[-1]["close"]
    all_values = sorted(df["close"].tolist())
    rank = sum(1 for v in all_values if v <= current)
    percentile = rank / len(all_values)

    return {
        "current_close": current,
        "percentile": round(percentile, 2),
        "data_points": len(all_values),
    }


# ================================================================
# 统一数据接口类
# ================================================================

class DataProvider:
    """统一数据接口 — 基于聚宽"""

    def __init__(self):
        _ensure_auth()

    # --- 行情 ---
    def get_realtime_quote(self, code: str) -> dict:
        return get_realtime_quote(code)

    def get_batch_quotes(self, codes: List[str]) -> Dict[str, dict]:
        return get_batch_quotes(codes)

    def get_klines(self, code: str, count: int = 120) -> List[dict]:
        return get_klines(code, count)

    # --- 财务+估值 ---
    def get_financials(self, code: str) -> dict:
        return get_financials_data(code)

    # --- 行业 ---
    def get_stock_industry(self, code: str) -> dict:
        return get_stock_industry(code)

    def get_stock_concepts(self, code: str) -> List[str]:
        return get_stock_concepts(code)

    def get_industry_ranking(self, dt: Optional[date] = None) -> List[dict]:
        return get_industry_ranking(dt)

    # --- 资金流 ---
    def get_money_flow(self, code: str, days: int = 20) -> List[dict]:
        return get_money_flow_data(code, days)

    def get_margin(self, code: str, days: int = 20) -> List[dict]:
        return get_margin_data(code, days)

    # --- 龙虎榜 ---
    def get_billboard(self, code: str, lookback: int = 30) -> List[dict]:
        return get_billboard_data(code, lookback=lookback)

    # --- 解禁 ---
    def get_lockup(self, code: str) -> dict:
        return get_lockup_data(code)

    # --- 市场情绪 ---
    def get_market_sentiment(self, dt: Optional[date] = None) -> dict:
        return get_market_sentiment(dt)

    def get_limit_up_stocks(self, dt: Optional[date] = None) -> List[dict]:
        return get_limit_up_stocks(dt)

    # --- 指数 ---
    def get_index_quote(self, index_code: str) -> dict:
        return get_index_quote(index_code)

    def get_index_pe_percentile(self, index_code: str = "000300.XSHG") -> dict:
        return get_index_pe_percentile(index_code)
