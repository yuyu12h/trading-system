"""
趋势线识别 — Python 版
逻辑与 pine/趋势线识别.pine 逐行对应
参数: pivot_left=10, pivot_right=10, max_pivots=50, pair_count=4
品种: XRPUSDT 日线 (Binance)
"""

import json
import os
import csv
import time
from datetime import datetime

import requests

# ====================================================================
# 0. 数据获取 (Binance API)
# ====================================================================

PROXY = {'http': 'http://127.0.0.1:7897', 'https': 'http://127.0.0.1:7897'}
OUT_CSV = '历史数据/XRPUSDT_1d_binance.csv'


def fetch_binance_klines(symbol='XRPUSDT', interval='1d', start_ms=None):
    """分页下载 Binance K 线，返回 [{date, open, high, low, close, volume}]"""
    url = 'https://api.binance.com/api/v3/klines'
    all_bars = []
    current_start = start_ms
    while True:
        params = {'symbol': symbol, 'interval': interval, 'limit': 1000}
        if current_start is not None:
            params['startTime'] = current_start
        # 先试无代理，失败走代理
        try:
            resp = requests.get(url, params=params, timeout=30)
        except Exception:
            resp = requests.get(url, params=params, proxies=PROXY, timeout=30)
        if resp.status_code != 200:
            print(f'  HTTP {resp.status_code}: {resp.text[:100]}')
            break
        bars = resp.json()
        if not bars:
            break
        all_bars.extend(bars)
        last_time = bars[-1][0]
        if current_start is not None and last_time <= current_start:
            break
        current_start = last_time + 1
        time.sleep(0.1)

    data = []
    for b in all_bars:
        data.append({
            'date': datetime.utcfromtimestamp(b[0] / 1000).strftime('%Y-%m-%d'),
            'open': float(b[1]), 'high': float(b[2]),
            'low': float(b[3]), 'close': float(b[4]),
            'volume': float(b[5]),
        })
    return data


def load_data():
    """优先读本地完整 Binance CSV (2018 至今)，否则从 API 下载"""
    csv_path = '历史数据/XRPUSDT_1d_binance_2018.csv'
    if os.path.exists(csv_path):
        data = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append({
                    'date': row['Date'],
                    'open': float(row['Open']), 'high': float(row['High']),
                    'low': float(row['Low']), 'close': float(row['Close']),
                    'volume': float(row.get('Volume', 0)),
                })
        return data

    # 本地没有则从 Binance API 下载完整历史
    print('下载 XRPUSDT 日线 (Binance) ...')
    start_ms = int(datetime(2018, 5, 1).timestamp() * 1000)
    return fetch_binance_klines('XRPUSDT', '1d', start_ms=start_ms)


# ====================================================================
# 1. 枢轴点检测 (等价 ta.pivothigh / ta.pivotlow, left/right 分开)
# ====================================================================

def detect_pivots(data, left=10, right=10):
    """检测枢轴高点/低点，返回 [(bar, price, shadow_lo_or_hi), ...]
    高点: (bar, high, u)   u = max(open, close) 上影线下沿
    低点: (bar, low,  l)   l = min(open, close) 下影线上沿
    """
    n = len(data)
    highs = []
    lows = []
    for i in range(left, n - right):
        h = data[i]['high']
        is_ph = True
        for j in range(1, left + 1):
            if data[i - j]['high'] >= h:
                is_ph = False
                break
        if is_ph:
            for j in range(1, right + 1):
                if data[i + j]['high'] >= h:
                    is_ph = False
                    break
        if is_ph:
            u = max(data[i]['open'], data[i]['close'])
            highs.append((i, h, u))

        l = data[i]['low']
        is_pl = True
        for j in range(1, left + 1):
            if data[i - j]['low'] <= l:
                is_pl = False
                break
        if is_pl:
            for j in range(1, right + 1):
                if data[i + j]['low'] <= l:
                    is_pl = False
                    break
        if is_pl:
            ll = min(data[i]['open'], data[i]['close'])
            lows.append((i, l, ll))
    return highs, lows


# ====================================================================
# 2. canAlign — 三点共线判定 (无极调节)
# 线由 B、C 定，往前延伸到 A，判定三个影线区间能否被同一条线穿过
# ====================================================================

def can_align(barA, loA, hiA, barB, loB, hiB, barC, loC, hiC):
    k = (barA - barB) / (barC - barB)
    yA_lo = loB * (1 - k) + hiC * k
    yA_hi = hiB * (1 - k) + loC * k
    return yA_lo <= hiA and yA_hi >= loA


# ====================================================================
# 3. getLine — 取可行解 (返回 A、C 连接点价格)
# ====================================================================

def get_line_high(barA, uA, highA, barB, uB, highB, barC, uC, highC):
    t = (barB - barA) / (barC - barA)
    yA = highA
    yC = highC
    yB = yA * (1 - t) + yC * t
    if yB > highB:
        yB = highB
        yA = (yB - yC * t) / (1 - t)
        if yA < uA:
            yA = uA
            yC = (yB - yA * (1 - t)) / t
    return yA, yC


def get_line_low(barA, lA, lowA, barB, lB, lowB, barC, lC, lowC):
    t = (barB - barA) / (barC - barA)
    yA = lowA
    yC = lowC
    yB = yA * (1 - t) + yC * t
    if yB < lowB:
        yB = lowB
        yA = (yB - yC * t) / (1 - t)
        if yA > lA:
            yA = lA
            yC = (yB - yA * (1 - t)) / t
    return yA, yC


# ====================================================================
# 4. 趋势线识别主逻辑 (与 pine 增量逻辑一致)
# ====================================================================

def find_trendlines(data, left=10, right=10, max_pivots=50, pair_count=4, max_span=400):
    highs, lows = detect_pivots(data, left, right)

    lines = []

    # ---- 下降趋势线 (连高点) ----
    for c_idx in range(1, len(highs)):
        barC, highC, uC = highs[c_idx]
        for b_off in range(1, pair_count + 1):
            b_idx = c_idx - b_off
            if b_idx < 0:
                break
            barB, highB, uB = highs[b_idx]
            if highC >= highB:  # 下降趋势线需递减高点
                continue
            slopeBC = (highC - highB) / (barC - barB)

            # B 到 C 之间的枢轴高点不能突破线
            mid_ok = True
            for m_idx in range(b_idx + 1, c_idx):
                barM, highM, _ = highs[m_idx]
                yMid = highB + slopeBC * (barM - barB)
                if highM > yMid:
                    mid_ok = False
                    break
            if not mid_ok:
                continue

            # 往前扫描，收集 canAlign 通过的候选 A
            candidates = []
            prev_touch_bar = barB
            lo_a = max(0, c_idx - (max_pivots - 1))
            a_idx = b_idx - 1
            while a_idx >= lo_a:
                barA, highA, uA = highs[a_idx]
                if can_align(barA, uA, highA, barB, uB, highB, barC, uC, highC):
                    if prev_touch_bar - barA > max_span:  # 相邻触点间隔超限
                        break
                    candidates.append(a_idx)
                    prev_touch_bar = barA
                else:
                    # 非触点，检查是否突破基准线（high 高于线）
                    yBase = highB + slopeBC * (barA - barB)
                    if highA > yBase:
                        break
                a_idx -= 1

            # 从远到近，找约束通过的 A
            for a_idx in reversed(candidates):
                barA, highA, uA = highs[a_idx]
                # A 须是 A→B 之间的最高枢轴高点（否则中间有更高点破坏递减结构）
                ok_high = True
                for m in range(a_idx + 1, b_idx):
                    if highs[m][1] > highA:
                        ok_high = False
                        break
                if not ok_high:
                    continue
                yA, yC = get_line_high(barA, uA, highA, barB, uB, highB, barC, uC, highC)
                if not (yA > yC):  # 下降趋势线需向下斜
                    continue
                slope = (yC - yA) / (barC - barA)
                ok = True
                for i in range(barA, barC + 1):
                    line_val = yA + slope * (i - barA)
                    if data[i]['close'] > line_val:
                        ok = False
                        break
                if ok:
                    # 触点间隔约束：确定的线穿过的触点，相邻间隔 ≤ max_span
                    prev_touch = barA
                    ok_span = True
                    for m in range(a_idx + 1, b_idx):
                        barM, highM, uM = highs[m]
                        line_val_m = yA + slope * (barM - barA)
                        if uM <= line_val_m <= highM:  # 影线被线穿过 = 触点
                            if barM - prev_touch > max_span:
                                ok_span = False
                                break
                            prev_touch = barM
                    if ok_span and barB - prev_touch <= max_span:
                        lines.append({
                            'type': 'down',
                            'a': {'bar': barA, 'date': data[barA]['date'], 'price': round(yA, 6)},
                            'c': {'bar': barC, 'date': data[barC]['date'], 'price': round(yC, 6)},
                            'b': {'bar': barB, 'date': data[barB]['date'], 'price': round(highB, 6)},
                        })
                        break

    # ---- 上升趋势线 (连低点) ----
    for c_idx in range(1, len(lows)):
        barC, lowC, lC = lows[c_idx]
        for b_off in range(1, pair_count + 1):
            b_idx = c_idx - b_off
            if b_idx < 0:
                break
            barB, lowB, lB = lows[b_idx]
            if lowC <= lowB:  # 上升趋势线需递增低点
                continue
            slopeBC = (lowC - lowB) / (barC - barB)

            # B 到 C 之间的枢轴低点不能跌破线
            mid_ok = True
            for m_idx in range(b_idx + 1, c_idx):
                barM, lowM, _ = lows[m_idx]
                yMid = lowB + slopeBC * (barM - barB)
                if lowM < yMid:
                    mid_ok = False
                    break
            if not mid_ok:
                continue

            # 往前扫描，收集 canAlign 通过的候选 A
            candidates = []
            prev_touch_bar = barB
            lo_a = max(0, c_idx - (max_pivots - 1))
            a_idx = b_idx - 1
            while a_idx >= lo_a:
                barA, lowA, lA = lows[a_idx]
                if can_align(barA, lowA, lA, barB, lowB, lB, barC, lowC, lC):
                    if prev_touch_bar - barA > max_span:  # 相邻触点间隔超限
                        break
                    candidates.append(a_idx)
                    prev_touch_bar = barA
                else:
                    # 非触点，检查是否跌破基准线（low 低于线）
                    yBase = lowB + slopeBC * (barA - barB)
                    if lowA < yBase:
                        break
                a_idx -= 1

            # 从远到近，找约束通过的 A
            for a_idx in reversed(candidates):
                barA, lowA, lA = lows[a_idx]
                # A 须是 A→B 之间的最低枢轴低点（否则中间有更低点破坏递增结构）
                ok_low = True
                for m in range(a_idx + 1, b_idx):
                    if lows[m][1] < lowA:
                        ok_low = False
                        break
                if not ok_low:
                    continue
                yA, yC = get_line_low(barA, lA, lowA, barB, lB, lowB, barC, lC, lowC)
                if not (yA < yC):  # 上升趋势线需向上斜
                    continue
                slope = (yC - yA) / (barC - barA)
                ok = True
                for i in range(barA, barC + 1):
                    line_val = yA + slope * (i - barA)
                    if data[i]['close'] < line_val:
                        ok = False
                        break
                if ok:
                    # 触点间隔约束：确定的线穿过的触点，相邻间隔 ≤ max_span
                    prev_touch = barA
                    ok_span = True
                    for m in range(a_idx + 1, b_idx):
                        barM, lowM, lM = lows[m]
                        line_val_m = yA + slope * (barM - barA)
                        if lowM <= line_val_m <= lM:  # 影线被线穿过 = 触点
                            if barM - prev_touch > max_span:
                                ok_span = False
                                break
                            prev_touch = barM
                    if ok_span and barB - prev_touch <= max_span:
                        lines.append({
                            'type': 'up',
                            'a': {'bar': barA, 'date': data[barA]['date'], 'price': round(yA, 6)},
                            'c': {'bar': barC, 'date': data[barC]['date'], 'price': round(yC, 6)},
                            'b': {'bar': barB, 'date': data[barB]['date'], 'price': round(lowB, 6)},
                        })
                        break

    return highs, lows, lines


# ====================================================================
# 5. 输出 + 可视化
# ====================================================================

def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    data = load_data()
    print(f'数据: XRPUSDT 日线, {len(data)} 根 ({data[0]["date"]} ~ {data[-1]["date"]})')

    left, right = 10, 10
    max_span = 400
    pair_count = 10
    highs, lows, lines = find_trendlines(data, left, right, max_span=max_span, pair_count=pair_count)
    print(f'枢轴高点: {len(highs)}  枢轴低点: {len(lows)}')
    print(f'趋势线总数: {len(lines)}')

    down = [l for l in lines if l['type'] == 'down']
    up = [l for l in lines if l['type'] == 'up']
    print(f'  下降趋势线: {len(down)}  上升趋势线: {len(up)}')

    # 保存 JSON
    out = {
        'symbol': 'XRPUSDT', 'interval': '1d', 'source': 'Binance',
        'params': {'pivot_left': left, 'pivot_right': right, 'max_pivots': 50, 'pair_count': pair_count, 'max_span': max_span},
        'data_range': [data[0]['date'], data[-1]['date']],
        'total_bars': len(data),
        'pivot_highs': len(highs), 'pivot_lows': len(lows),
        'trendline_count': len(lines),
        'down_count': len(down), 'up_count': len(up),
        'trendlines': lines,
    }
    json_path = '_xrpusdt_binance_trendline.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'已保存: {json_path}')

    # 打印示例
    print('\n--- 下降趋势线示例 (前 5 条) ---')
    for l in down[:5]:
        print(f"  {l['a']['date']}({l['a']['price']}) -> {l['c']['date']}({l['c']['price']})  中间锚点 {l['b']['date']}")
    print('--- 上升趋势线示例 (前 5 条) ---')
    for l in up[:5]:
        print(f"  {l['a']['date']}({l['a']['price']}) -> {l['c']['date']}({l['c']['price']})  中间锚点 {l['b']['date']}")

    # 可视化
    try:
        plot(data, lines, left, right)
    except Exception as e:
        print(f'可视化跳过: {e}')


def plot(data, lines, left, right):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    n = len(data)
    xs = list(range(n))
    closes = [d['close'] for d in data]

    fig, ax = plt.subplots(figsize=(20, 10))
    ax.plot(xs, closes, color='#888888', linewidth=0.6, alpha=0.5, label='close')

    for l in lines:
        color = '#ef5350' if l['type'] == 'down' else '#26a69a'
        ax.plot([l['a']['bar'], l['c']['bar']],
                [l['a']['price'], l['c']['price']],
                color=color, linewidth=1.0, alpha=0.7)

    ax.set_title('XRPUSDT Daily Trendlines (pivot L/R=10, pair=4, 3-point align)')
    ax.legend()
    ax.grid(True, alpha=0.3)
    png_path = '_xrpusdt_binance_trendline.png'
    fig.savefig(png_path, dpi=100, bbox_inches='tight')
    print(f'已保存图表: {png_path}')


if __name__ == '__main__':
    main()
