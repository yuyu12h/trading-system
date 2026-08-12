"""
双顶双底识别 — Python 回测版
逻辑与 pine/双顶双底识别.pine 一致
参数: pivot_lookback=6, atr_period=14, atr_mult=1.0, search_win=5, strict_mode=True
品种: BCHUSD 日线
"""

import json, os, csv, math
from datetime import datetime

# ====================================================================
# 0. 获取数据
# ====================================================================

def fetch_data(csv_path="历史数据/BCH_USD_1d.csv"):
    """从本地 CSV 读取日线数据"""
    import csv, os
    data = []
    full_path = os.path.join(os.path.dirname(__file__), csv_path) if not os.path.isabs(csv_path) else csv_path
    with open(full_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append({
                'date': row['Date'],
                'open':  float(row['Open']),
                'high':  float(row['High']),
                'low':   float(row['Low']),
                'close': float(row['Close']),
                'volume': float(row['Volume']) if row.get('Volume') else 0,
            })
    return data

# ====================================================================
# 1. 计算 ATR
# ====================================================================

def calc_atr(data, period=14):
    """计算 ATR 序列"""
    atr = [0.0] * len(data)
    tr_sum = 0.0
    for i in range(len(data)):
        if i == 0:
            tr = data[i]['high'] - data[i]['low']
        else:
            tr = max(
                data[i]['high'] - data[i]['low'],
                abs(data[i]['high'] - data[i-1]['close']),
                abs(data[i]['low']  - data[i-1]['close'])
            )
        if i < period:
            tr_sum += tr
            atr[i] = tr_sum / (i + 1)
        else:
            atr[i] = (atr[i-1] * (period - 1) + tr) / period
    return atr

# ====================================================================
# 2. 枢轴点检测 (等价 ta.pivothigh / ta.pivotlow)
# ====================================================================

def detect_pivots(data, lookback=6):
    """
    检测枢轴高低点
    返回: highs = [(bar_index, price), ...], lows = [(bar_index, price), ...]
    """
    n = len(data)
    highs = []
    lows = []
    for i in range(lookback, n - lookback):
        # 检查是否为枢轴高点
        h = data[i]['high']
        is_ph = True
        for j in range(1, lookback + 1):
            if data[i - j]['high'] >= h or data[i + j]['high'] >= h:
                is_ph = False
                break
        if is_ph:
            highs.append((i, h))

        # 检查是否为枢轴低点
        l = data[i]['low']
        is_pl = True
        for j in range(1, lookback + 1):
            if data[i - j]['low'] <= l or data[i + j]['low'] <= l:
                is_pl = False
                break
        if is_pl:
            lows.append((i, l))

    return highs, lows

# ====================================================================
# 3. 辅助函数
# ====================================================================

def is_skippable(pk_price, pi_price, pj_price, tolerance):
    """中间枢轴价格与两端都 > tolerance"""
    return abs(pk_price - pi_price) > tolerance and abs(pk_price - pj_price) > tolerance

def find_lowest_between(data, bar1, bar2):
    """在 bar1..bar2 之间找最低 low"""
    lo = float('inf')
    lo_bar = bar1
    for i in range(bar1, bar2 + 1):
        if data[i]['low'] < lo:
            lo = data[i]['low']
            lo_bar = i
    return lo, lo_bar

def find_highest_between(data, bar1, bar2):
    """在 bar1..bar2 之间找最高 high"""
    hi = -float('inf')
    hi_bar = bar1
    for i in range(bar1, bar2 + 1):
        if data[i]['high'] > hi:
            hi = data[i]['high']
            hi_bar = i
    return hi, hi_bar

def is_recorded_pivot(bar_idx, pivots):
    """检查 bar_idx 是否在枢轴列表中"""
    for bar, _ in pivots:
        if bar == bar_idx:
            return True
    return False

# ====================================================================
# 4. 主检测逻辑
# ====================================================================

def detect_patterns(data, pivot_lookback=6, atr_period=14, atr_mult=1.0,
                    search_win=5, strict_mode=True, max_pending=200):
    """
    检测双顶双底
    返回: list of dicts
    """
    n = len(data)
    atr_arr = calc_atr(data, atr_period)
    highs, lows = detect_pivots(data, pivot_lookback)

    print(f"数据: {len(data)} 根K线 | 日期范围: {data[0]['date']} ~ {data[-1]['date']}")
    print(f"参数: pivot_lookback={pivot_lookback}, atr={atr_period}, atr_mult={atr_mult}, search_win={search_win}, strict={strict_mode}")
    print(f"枢轴点: 高点{len(highs)}个, 低点{len(lows)}个")
    print()

    # 维护最近的 search_win 个枢轴
    ph_queue = []  # [(bar, price)]
    pl_queue = []

    pending = []  # 待确认候选
    confirmed_patterns = []

    for bar_idx in range(n):
        atr_val = atr_arr[bar_idx]
        if atr_val <= 0:
            continue

        # ── 检查是否有新枢轴高点 ──
        for h_bar, h_price in highs:
            if h_bar == bar_idx:
                ph_queue.insert(0, (h_bar, h_price))
                if len(ph_queue) > search_win:
                    ph_queue.pop()
                # 弹性搜索配对
                search_double_top(ph_queue, bar_idx, h_price, atr_val, atr_mult,
                                  data, highs, lows, strict_mode, pending)
                break

        # ── 检查是否有新枢轴低点 ──
        for l_bar, l_price in lows:
            if l_bar == bar_idx:
                pl_queue.insert(0, (l_bar, l_price))
                if len(pl_queue) > search_win:
                    pl_queue.pop()
                search_double_bottom(pl_queue, bar_idx, l_price, atr_val, atr_mult,
                                     data, highs, lows, strict_mode, pending)
                break

        # ── 每 bar 检查待确认候选 ──
        to_remove = []
        for idx, cand in enumerate(pending):
            age = bar_idx - cand['top2_bar']
            if age > max_pending:
                to_remove.append(idx)
                continue

            lookback = min(age, 500)
            confirmed = False
            invalidated = False

            if cand['is_double_top']:
                inval_level = max(cand['top1_price'], cand['top2_price'])
                o = lookback
                while o >= 0 and not confirmed and not invalidated:
                    if bar_idx - o >= n:
                        o -= 1
                        continue
                    if data[bar_idx - o]['high'] > inval_level:
                        invalidated = True
                    if data[bar_idx - o]['low'] <= cand['neck_price']:
                        confirmed = True
                    o -= 1
            else:
                inval_level = min(cand['top1_price'], cand['top2_price'])
                o = lookback
                while o >= 0 and not confirmed and not invalidated:
                    if bar_idx - o >= n:
                        o -= 1
                        continue
                    if data[bar_idx - o]['low'] < inval_level:
                        invalidated = True
                    if data[bar_idx - o]['high'] >= cand['neck_price']:
                        confirmed = True
                    o -= 1

            if invalidated:
                to_remove.append(idx)
            elif confirmed:
                pattern = {
                    'type': '双顶' if cand['is_double_top'] else '双底',
                    'top1_bar': cand['top1_bar'],
                    'top1_date': data[cand['top1_bar']]['date'],
                    'top1_price': round(cand['top1_price'], 4),
                    'top2_bar': cand['top2_bar'],
                    'top2_date': data[cand['top2_bar']]['date'],
                    'top2_price': round(cand['top2_price'], 4),
                    'neck_price': round(cand['neck_price'], 4),
                    'confirm_bar': bar_idx,
                    'confirm_date': data[bar_idx]['date'],
                }
                confirmed_patterns.append(pattern)
                to_remove.append(idx)

        # 倒序删除
        for idx in sorted(to_remove, reverse=True):
            del pending[idx]

    return confirmed_patterns


def search_double_top(ph_queue, bar_idx, pivot_price, atr_val, atr_mult,
                      data, highs, lows, strict_mode, pending):
    sz = len(ph_queue)
    if sz < 2:
        return
    tolerance = atr_mult * atr_val
    new_bar, new_price = ph_queue[0]

    for j in range(1, sz):
        old_bar, old_price = ph_queue[j]

        if abs(new_price - old_price) > tolerance:
            continue

        pattern_high = max(new_price, old_price)
        intermediates_ok = True
        if j > 1:
            for k in range(1, j):
                mid_bar, mid_price = ph_queue[k]
                if mid_bar > old_bar and mid_bar < new_bar:
                    if not is_skippable(mid_price, old_price, new_price, tolerance):
                        intermediates_ok = False
                        break
                    if mid_price > pattern_high:
                        intermediates_ok = False
                        break
        if not intermediates_ok:
            continue

        if strict_mode:
            # 严格模式: 找两顶之间最低的枢轴低点作为颈线
            mid_low = float('inf')
            mid_low_bar = -1
            for l_bar, l_price in lows:
                if old_bar < l_bar < new_bar and l_price < mid_low:
                    mid_low = l_price
                    mid_low_bar = l_bar
            if mid_low_bar < 0:
                continue
        else:
            mid_low, mid_low_bar = find_lowest_between(data, old_bar, new_bar)

        cand = {
            'is_double_top': True,
            'top1_bar': old_bar,
            'top1_price': old_price,
            'top2_bar': new_bar,
            'top2_price': new_price,
            'neck_price': mid_low,
        }
        pending.append(cand)


def search_double_bottom(pl_queue, bar_idx, pivot_price, atr_val, atr_mult,
                         data, highs, lows, strict_mode, pending):
    sz = len(pl_queue)
    if sz < 2:
        return
    tolerance = atr_mult * atr_val
    new_bar, new_price = pl_queue[0]

    for j in range(1, sz):
        old_bar, old_price = pl_queue[j]

        if abs(new_price - old_price) > tolerance:
            continue

        pattern_low = min(new_price, old_price)
        intermediates_ok = True
        if j > 1:
            for k in range(1, j):
                mid_bar, mid_price = pl_queue[k]
                if mid_bar > old_bar and mid_bar < new_bar:
                    if not is_skippable(mid_price, old_price, new_price, tolerance):
                        intermediates_ok = False
                        break
                    if mid_price < pattern_low:
                        intermediates_ok = False
                        break
        if not intermediates_ok:
            continue

        if strict_mode:
            # 严格模式: 找两底之间最高的枢轴高点作为颈线
            mid_high = -float('inf')
            mid_high_bar = -1
            for h_bar, h_price in highs:
                if old_bar < h_bar < new_bar and h_price > mid_high:
                    mid_high = h_price
                    mid_high_bar = h_bar
            if mid_high_bar < 0:
                continue
        else:
            mid_high, mid_high_bar = find_highest_between(data, old_bar, new_bar)

        cand = {
            'is_double_top': False,
            'top1_bar': old_bar,
            'top1_price': old_price,
            'top2_bar': new_bar,
            'top2_price': new_price,
            'neck_price': mid_high,
        }
        pending.append(cand)

# ====================================================================
# 5. 主程序
# ====================================================================

if __name__ == '__main__':
    data = fetch_data("历史数据/BCH_USD_1d_full.csv")

    for mode_name, strict_val in [("严格模式", True), ("宽松模式", False)]:
        print("=" * 70)
        print(f"双顶双底识别 — BCHUSD 日线 | ATR倍数=1.0 | {mode_name}")
        print("=" * 70)
        print()

        results = detect_patterns(
            data,
            pivot_lookback=6,
            atr_period=14,
            atr_mult=1.0,
            search_win=5,
            strict_mode=strict_val,
            max_pending=200,
        )

        print(f"共识别到 {len(results)} 个形态")
        print()

        results.sort(key=lambda x: x['confirm_date'])

        for i, r in enumerate(results, 1):
            top1_info = f"{r['top1_date']} @ {r['top1_price']}"
            top2_info = f"{r['top2_date']} @ {r['top2_price']}"
            if r['type'] == '双顶':
                height = round(abs(r['top2_price'] - r['neck_price']), 2)
            else:
                height = round(abs(r['neck_price'] - r['top2_price']), 2)
            print(f"[{i:2d}] {r['type']} | 确认: {r['confirm_date']}")
            print(f"     顶1: {top1_info} | 顶2: {top2_info}")
            print(f"     颈线: {r['neck_price']} | 形态高度: {height}")

        # ── 输出 JSON ──
        output = {
            'params': {
                'symbol': 'BCHUSD',
                'interval': '1d',
                'pivot_lookback': 6,
                'atr_period': 14,
                'atr_mult': 1.0,
                'search_win': 5,
                'strict_mode': strict_val,
                'max_pending_bars': 200,
            },
            'data_range': f"{data[0]['date']} ~ {data[-1]['date']}",
            'total_bars': len(data),
            'patterns_found': len(results),
            'patterns': results,
        }
        suffix = 'strict' if strict_val else 'loose'
        json_path = f'D:/cursor/firstcc/_bchusd_double_patterns_{suffix}.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print()
        print(f"完整结果已写入: {json_path}")
        print()
