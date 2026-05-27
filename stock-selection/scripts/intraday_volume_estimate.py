"""
盘中预估全天成交量工具

A股交易时间：
- 上午：09:30 - 11:30（120分钟）
- 下午：13:00 - 15:00（120分钟）
- 全天共 240 分钟

提供三种预估方法：
1. 线性外推法：当前成交额 × (240 / 已过分钟数)
2. U型分布加权法：基于A股日内成交量经验分布权重
3. 量比推算法：前5日均量 × 量比

用法：
    python intraday_volume_estimate.py 603290
    python intraday_volume_estimate.py 603290 --avg5 195000
"""

import urllib.request
import sys
from datetime import datetime


# A股日内成交量经验分布（每30分钟占全天比重）
# 呈"U型"——开盘和尾盘量大，午盘量小
INTRADAY_WEIGHT = [
    0.18,  # 09:30-10:00 开盘半小时（量最大）
    0.13,  # 10:00-10:30
    0.10,  # 10:30-11:00
    0.09,  # 11:00-11:30（午盘前最低）
    0.11,  # 13:00-13:30
    0.10,  # 13:30-14:00
    0.12,  # 14:00-14:30
    0.17,  # 14:30-15:00 尾盘半小时（量次大）
]


def calc_elapsed_minutes(h, m):
    """计算从开盘到当前已过的交易分钟数"""
    current_time = h * 60 + m
    open_am = 9 * 60 + 30    # 09:30
    close_am = 11 * 60 + 30  # 11:30
    open_pm = 13 * 60        # 13:00
    close_pm = 15 * 60       # 15:00

    if current_time <= open_am:
        return 0
    elif current_time <= close_am:
        return current_time - open_am
    elif current_time <= open_pm:
        return 120  # 上午全部120分钟
    elif current_time <= close_pm:
        return 120 + (current_time - open_pm)
    else:
        return 240  # 已收盘


def get_elapsed_weight(elapsed_min):
    """根据已过分钟数，计算已完成的成交量权重占比（U型分布）"""
    full_periods = elapsed_min // 30
    remaining = elapsed_min % 30

    weight = 0.0
    for i in range(min(int(full_periods), 8)):
        weight += INTRADAY_WEIGHT[i]

    # 当前未完成时段按线性插值
    if full_periods < 8 and remaining > 0:
        weight += INTRADAY_WEIGHT[int(full_periods)] * (remaining / 30)

    return weight


def get_realtime_quote(code):
    """腾讯财经API获取实时行情"""
    if code.startswith(("6", "9")):
        prefix = "sh"
    elif code.startswith("8"):
        prefix = "bj"
    else:
        prefix = "sz"

    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")
    vals = data.split('"')[1].split("~")

    if len(vals) < 53:
        raise ValueError(f"数据字段不足: {len(vals)}")

    return {
        "name": vals[1],
        "price": float(vals[3]) if vals[3] else 0,
        "change_pct": float(vals[32]) if vals[32] else 0,
        "amount_wan": float(vals[37]) if vals[37] else 0,
        "turnover_pct": float(vals[38]) if vals[38] else 0,
        "vol_ratio": float(vals[49]) if vals[49] else 0,
    }


def estimate_daily_volume(code, avg_5day_amount_wan=None):
    """
    盘中预估全天成交量。

    参数:
        code: 6位股票代码
        avg_5day_amount_wan: 前5日日均成交额（万元），None则用量比反推

    返回:
        dict: 包含三种方法的预估结果和综合判断
    """
    quote = get_realtime_quote(code)
    now = datetime.now()
    elapsed = calc_elapsed_minutes(now.hour, now.minute)
    total_minutes = 240

    result = {
        "code": code,
        "name": quote["name"],
        "time": now.strftime("%H:%M"),
        "elapsed_min": elapsed,
        "elapsed_pct": elapsed / total_minutes * 100,
        "current_amount_wan": quote["amount_wan"],
        "change_pct": quote["change_pct"],
        "vol_ratio": quote["vol_ratio"],
        "estimates": {},
        "conclusion": "",
    }

    if elapsed == 0:
        result["conclusion"] = "未开盘，无法预估"
        return result

    # 方法1：线性外推
    linear = quote["amount_wan"] * (total_minutes / elapsed)
    result["estimates"]["linear"] = linear

    # 方法2：U型加权
    weight = get_elapsed_weight(elapsed)
    weighted = quote["amount_wan"] / weight if weight > 0 else 0
    result["estimates"]["weighted"] = weighted
    result["elapsed_weight"] = weight

    # 方法3：量比推算
    if avg_5day_amount_wan:
        vol_ratio_est = avg_5day_amount_wan * quote["vol_ratio"]
    else:
        # 反推前5日均量：量比 = 当前量 / (5日均量 × elapsed/240)
        # 5日均量 = 当前量 / (量比 × elapsed/240)
        if quote["vol_ratio"] > 0:
            implied_avg5 = quote["amount_wan"] / (quote["vol_ratio"] * elapsed / total_minutes)
            avg_5day_amount_wan = implied_avg5
            vol_ratio_est = implied_avg5 * quote["vol_ratio"]
        else:
            vol_ratio_est = 0
    result["estimates"]["vol_ratio"] = vol_ratio_est
    result["avg_5day_amount_wan"] = avg_5day_amount_wan

    # 综合均值
    estimates = [v for v in result["estimates"].values() if v > 0]
    avg_est = sum(estimates) / len(estimates) if estimates else 0
    result["estimates"]["average"] = avg_est

    # 放量判断
    if avg_5day_amount_wan and avg_5day_amount_wan > 0:
        ratio = avg_est / avg_5day_amount_wan
        result["volume_ratio_to_avg5"] = ratio
        if ratio >= 2.0:
            result["conclusion"] = f"显著放量（预估{ratio:.1f}倍于5日均量）"
        elif ratio >= 1.5:
            result["conclusion"] = f"明显放量（预估{ratio:.1f}倍于5日均量）"
        elif ratio >= 1.2:
            result["conclusion"] = f"温和放量（预估{ratio:.1f}倍于5日均量）"
        elif ratio >= 0.8:
            result["conclusion"] = f"平量（预估{ratio:.1f}倍于5日均量）"
        else:
            result["conclusion"] = f"缩量（预估{ratio:.1f}倍于5日均量）"

        # 量价配合
        if ratio >= 1.5 and quote["change_pct"] > 3:
            result["price_volume"] = "放量上涨：量价齐升，主力积极进场"
        elif ratio >= 1.5 and quote["change_pct"] < -3:
            result["price_volume"] = "放量下跌：恐慌抛售或主力出货"
        elif ratio < 1.0 and quote["change_pct"] > 3:
            result["price_volume"] = "缩量上涨：上涨缺乏量能支撑，持续性存疑"
        elif ratio >= 1.2 and quote["change_pct"] > 0:
            result["price_volume"] = "温和放量上涨：健康上涨形态"
        elif ratio < 1.0 and quote["change_pct"] < -3:
            result["price_volume"] = "缩量下跌：恐慌情绪不重，可能企稳"
        else:
            result["price_volume"] = "量价关系中性"

    return result


def print_report(result):
    """打印预估报告"""
    print(f"=== {result['name']}({result['code']}) 盘中成交量预估 ===")
    print(f"当前时间: {result['time']}")
    print(f"已过交易时间: {result['elapsed_min']}/240分钟 ({result['elapsed_pct']:.1f}%)")
    print(f"当前成交额: {result['current_amount_wan']:.0f}万 ({result['current_amount_wan']/10000:.2f}亿)")
    print(f"当前涨跌幅: {result['change_pct']}%")
    print(f"量比: {result['vol_ratio']}")
    print()

    if result.get("elapsed_weight"):
        print(f"U型分布已完成权重: {result['elapsed_weight']:.3f} ({result['elapsed_weight']*100:.1f}%)")
    if result.get("avg_5day_amount_wan"):
        print(f"前5日日均成交额: {result['avg_5day_amount_wan']:.0f}万 ({result['avg_5day_amount_wan']/10000:.2f}亿)")
    print()

    print("--- 预估全天成交额 ---")
    est = result["estimates"]
    print(f"  方法1 线性外推: {est.get('linear', 0)/10000:.2f}亿")
    print(f"  方法2 U型加权: {est.get('weighted', 0)/10000:.2f}亿")
    print(f"  方法3 量比推算: {est.get('vol_ratio', 0)/10000:.2f}亿")
    print(f"  综合均值:       {est.get('average', 0)/10000:.2f}亿")
    print()

    if result.get("volume_ratio_to_avg5"):
        print(f"预估全天量/前5日均量 = {result['volume_ratio_to_avg5']:.2f}倍")
    print(f"结论: {result['conclusion']}")
    if result.get("price_volume"):
        print(f"量价配合: {result['price_volume']}")


if __name__ == "__main__":
    stock_code = sys.argv[1] if len(sys.argv) > 1 else "603290"
    avg5 = None
    if "--avg5" in sys.argv:
        idx = sys.argv.index("--avg5")
        avg5 = float(sys.argv[idx + 1])

    result = estimate_daily_volume(stock_code, avg_5day_amount_wan=avg5)
    print_report(result)
