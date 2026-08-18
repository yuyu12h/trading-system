"""
三角形态识别 — Python 验证版 v3
在 v2 逻辑基础上:
  1. 去掉 has_extra_pivots (内部额外触点) 过滤, 回到 v1 识别骨架
  2. 新增 0.618 回调必要条件 (熊大第5章: 收敛形态 = 回调到前一段 0.618 有反应)

4 触点 (时间顺序, 高点触发为例): 低1(d) → 高1(B) → 低2(L) → 高2(a)
  段1 = d → B  (上涨)
  段2 = B → L  (回调)
  段3 = L → a  (恢复上涨)

必要条件 (不满足则不画三角形):
  段2 回调 >= 段1 的 0.618    =>  (B_price - L_price) >= 0.618 * (B_price - d_price)
  段3 恢复 >= 段2 的 0.618    =>  (a_price - L_price) >= 0.618 * (B_price - L_price)
下降方向 (低点触发) 完全对称。
(>= 0.618 即"有反应", 不引入 0.786 / 容差)
"""

import csv, os, math, json

# ====================================================================
# 0. 数据
# ====================================================================

def fetch_data(csv_path="历史数据/XRP_USD_1d_2023.csv"):
    data = []
    full = os.path.join(os.path.dirname(os.path.abspath(__file__)), csv_path) if not os.path.isabs(csv_path) else csv_path
    with open(full, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            data.append({
                'date':  row['Date'],
                'open':  float(row['Open']),
                'high':  float(row['High']),
                'low':   float(row['Low']),
                'close': float(row['Close']),
            })
    return data

# ====================================================================
# 1. ATR (Wilder)
# ====================================================================

def calc_atr(data, period=14):
    atr = [0.0] * len(data)
    tr_sum = 0.0
    for i in range(len(data)):
        if i == 0:
            tr = data[i]['high'] - data[i]['low']
        else:
            tr = max(data[i]['high'] - data[i]['low'],
                     abs(data[i]['high'] - data[i-1]['close']),
                     abs(data[i]['low']  - data[i-1]['close']))
        if i < period:
            tr_sum += tr
            atr[i] = tr_sum / (i + 1)
        else:
            atr[i] = (atr[i-1] * (period - 1) + tr) / period
    return atr

# ====================================================================
# 2. 枢轴点 (等价 ta.pivothigh / ta.pivotlow, 左6右6)
# ====================================================================

def detect_pivots(data, lookback=6):
    n = len(data)
    highs, lows = [], []
    for i in range(lookback, n - lookback):
        h = data[i]['high']
        is_ph = True
        for j in range(1, lookback + 1):
            if data[i-j]['high'] >= h or data[i+j]['high'] >= h:
                is_ph = False
                break
        if is_ph:
            highs.append((i, h))

        l = data[i]['low']
        is_pl = True
        for j in range(1, lookback + 1):
            if data[i-j]['low'] <= l or data[i+j]['low'] <= l:
                is_pl = False
                break
        if is_pl:
            lows.append((i, l))
    return highs, lows

# ====================================================================
# 3. 几何工具
# ====================================================================

def line_price(bar0, price0, bar1, price1, bar_x):
    """两点连线在 bar_x 处的价格 (线性插值/外推)"""
    if bar0 == bar1:
        return price0
    return price0 + (price1 - price0) * (bar_x - bar0) / (bar1 - bar0)

def body_low(c):
    return min(c['open'], c['close'])

def body_high(c):
    return max(c['open'], c['close'])

# 影线重合 (下影线 [low, body_low])
def low_shadow_overlap(data, bar_a, price_a, bar_b, price_b):
    a_lo = price_a   # 枢轴低点 price 即 low
    a_bl = body_low(data[bar_a])
    b_lo = price_b
    b_bl = body_low(data[bar_b])
    return max(a_lo, b_lo) <= min(a_bl, b_bl)

# 影线重合 (上影线 [body_high, high])
def high_shadow_overlap(data, bar_a, price_a, bar_b, price_b):
    a_hi = price_a   # 枢轴高点 price 即 high
    a_bh = body_high(data[bar_a])
    b_hi = price_b
    b_bh = body_high(data[bar_b])
    return min(a_hi, b_hi) >= max(a_bh, b_bh)

# ====================================================================
# 4. 低点队列里找区间内最值
# ====================================================================

def lowest_low_between(queue, bar1, bar2):
    """queue 里 bar 落在 (bar1, bar2) 的最低低点, 返回 (price, bar), 无则 (inf,-1)"""
    best_p, best_b = float('inf'), -1
    for b, p in queue:
        if bar1 < b < bar2 and p < best_p:
            best_p, best_b = p, b
    return best_p, best_b

def highest_high_between(queue, bar1, bar2):
    best_p, best_b = -float('inf'), -1
    for b, p in queue:
        if bar1 < b < bar2 and p > best_p:
            best_p, best_b = p, b
    return best_p, best_b

# ====================================================================
# 5. 下边界方向判定 (高点触发时用)
# ====================================================================

def classify_dn_dir(data, d_bar, d_price, L_bar, L_price):
    """下边界 [d(早), L(晚)] 方向: 'up' / 'flat' / 'down'"""
    # 影线重合
    if low_shadow_overlap(data, d_bar, d_price, L_bar, L_price):
        return 'flat'
    # 假跌破: L 阴线跌破 d 收 d 下, 下一根阳线收回 d 上
    if L_bar + 1 < len(data):
        lc = data[L_bar]
        nc = data[L_bar + 1]
        if lc['close'] < lc['open'] and nc['close'] > nc['open']:
            if lc['close'] < d_price and nc['close'] > d_price:
                return 'flat'
    if L_price > d_price:
        return 'up'
    return 'down'

# 上边界方向判定 (低点触发时用), 对称
def classify_up_dir(data, d_bar, d_price, L_bar, L_price):
    if high_shadow_overlap(data, d_bar, d_price, L_bar, L_price):
        return 'flat'
    if L_bar + 1 < len(data):
        lc = data[L_bar]
        nc = data[L_bar + 1]
        if lc['close'] > lc['open'] and nc['close'] < nc['open']:
            if lc['close'] > d_price and nc['close'] < d_price:
                return 'flat'
    if L_price < d_price:
        return 'down'
    return 'up'

# ====================================================================
# 6. 结果记录
# ====================================================================

def record(drawn, seen, ttype, up_line, dn_line):
    """去重: 相同端点组合(上边界+下边界+类型)只画一次"""
    key = []
    if up_line:
        key.append(('up', up_line['start'][0], up_line['end'][0]))
    if dn_line:
        key.append(('dn', dn_line['start'][0], dn_line['end'][0]))
    key.append(('t', ttype))
    key = tuple(key)
    if key in seen:
        return
    seen.add(key)
    drawn.append({'triangle': ttype, 'up': up_line, 'dn': dn_line})

# ====================================================================
# 6.5 v3 新增: 0.618 回调必要条件
# ====================================================================

def fibo_ok_up(B_price, d_price, L_price, a_price):
    """高点触发 (上升结构 d->B->L->a):
       段1=d->B 段2=B->L(回调) 段3=L->a(恢复)
       段2 回调 >= 段1 的 0.618, 段3 恢复 >= 段2 的 0.618
       通过返回 (r2, r3), 否则 None
    """
    seg1 = B_price - d_price
    seg2 = B_price - L_price
    seg3 = a_price - L_price
    if seg1 <= 0 or seg2 <= 0 or seg3 <= 0:
        return None
    r2 = seg2 / seg1
    r3 = seg3 / seg2
    if r2 >= 0.618 and r3 >= 0.618:
        return (r2, r3)
    return None

def fibo_ok_dn(d_price, B_price, L_price, a_price):
    """低点触发 (下降结构 d->B->L->a, d 高点 B 低点 L 高点 a 低点):
       段1=d->B 段2=B->L(反弹) 段3=L->a(再跌)
       段2 反弹 >= 段1 的 0.618, 段3 再跌 >= 段2 的 0.618
       通过返回 (r2, r3), 否则 None
    """
    seg1 = d_price - B_price
    seg2 = L_price - B_price
    seg3 = L_price - a_price
    if seg1 <= 0 or seg2 <= 0 or seg3 <= 0:
        return None
    r2 = seg2 / seg1
    r3 = seg3 / seg2
    if r2 >= 0.618 and r3 >= 0.618:
        return (r2, r3)
    return None

# ====================================================================
# 7. 高点触发流程
# ====================================================================

def handle_ph(ph_queue, pl_queue, data, atr_val, tol, drawn, seen):
    """a = ph_queue[0] (最新高点)"""
    a_bar, a_price = ph_queue[0]
    sz = len(ph_queue)

    # 2. 定线: a 连更早高点, B 必须比 a 高(下降), 中间不突破
    for k in range(1, sz):
        B_bar, B_price = ph_queue[k]
        if B_price <= a_price:          # 上边界天然下降: B 更高
            continue
        ok = True
        for m in range(1, k):
            m_bar, m_price = ph_queue[m]
            lp = line_price(B_bar, B_price, a_bar, a_price, m_bar)
            if m_price > lp:            # 中间高点突破连线
                ok = False
                break
        if not ok:
            continue

        # 3. 找 L: B-a 之间最低枢轴低点
        L_price, L_bar = lowest_low_between(pl_queue, B_bar, a_bar)
        if L_bar < 0:
            continue

        # 上边界基本线 (端点 B -> a)
        up_base = {'start': [B_bar, B_price], 'end': [a_bar, a_price], 'points': [[B_bar, B_price], [a_bar, a_price]]}

        # 4. 类型1(上边界延长): B 回望更早高点, 共线的都延长
        for c_bar, c_price in ph_queue[k+1:]:
            if c_price <= B_price:
                continue
            ext = line_price(B_bar, B_price, a_bar, a_price, c_bar)
            if abs(c_price - ext) <= tol:
                # 共线, 延长线 c -> a
                record(drawn, seen, None, {
                    'start': [c_bar, c_price], 'end': [a_bar, a_price],
                    'points': [[c_bar, c_price], [B_bar, B_price], [a_bar, a_price]],
                }, None)

        # 5. 类型2(下边界构建): B 回望更早高点 c, 找 c-B 之间最低低点 d
        for c_bar, c_price in ph_queue[k+1:]:
            d_price, d_bar = lowest_low_between(pl_queue, c_bar, B_bar)
            if d_bar < 0:
                continue
            # d-L 连线不被其他低点突破
            dn_ok = True
            for l_bar, l_price in pl_queue:
                if d_bar < l_bar < L_bar:
                    lp = line_price(d_bar, d_price, L_bar, L_price, l_bar)
                    if l_price < lp:    # 低点跌破下边界
                        dn_ok = False
                        break
            if not dn_ok:
                continue

            # 6. 下边界方向
            dn_dir = classify_dn_dir(data, d_bar, d_price, L_bar, L_price)
            if dn_dir == 'down':
                continue

            # 6.5 v3: 0.618 回调必要条件 (d -> B -> L -> a)
            fibo = fibo_ok_up(B_price, d_price, L_price, a_price)
            if fibo is None:
                continue
            up_base['fibo'] = {'r2': round(fibo[0], 4), 'r3': round(fibo[1], 4)}

            # 8. 类型
            ttype = '对称三角' if dn_dir == 'up' else '下降三角'

            # 7. 下边界延长: d 回望更早低点, 共线的都延长
            dn_points = [[d_bar, d_price], [L_bar, L_price]]
            dn_start = [d_bar, d_price]
            for e_bar, e_price in pl_queue:
                if e_bar >= d_bar:
                    continue
                if dn_dir == 'up':
                    ext = line_price(d_bar, d_price, L_bar, L_price, e_bar)
                    if abs(e_price - ext) <= tol and e_price < d_price:
                        dn_points.insert(0, [e_bar, e_price])
                        dn_start = [e_bar, e_price]
                else:  # flat
                    if low_shadow_overlap(data, e_bar, e_price, d_bar, d_price):
                        dn_points.insert(0, [e_bar, e_price])
                        dn_start = [e_bar, e_price]

            dn_line = {'start': dn_start, 'end': [L_bar, L_price], 'points': dn_points}
            record(drawn, seen, ttype, up_base, dn_line)

# ====================================================================
# 8. 低点触发流程 (完全对称)
# ====================================================================

def handle_pl(pl_queue, ph_queue, data, atr_val, tol, drawn, seen):
    a_bar, a_price = pl_queue[0]
    sz = len(pl_queue)

    # 定线: a 连更早低点, B 必须比 a 低(上升)
    for k in range(1, sz):
        B_bar, B_price = pl_queue[k]
        if B_price >= a_price:          # 下边界天然上升: B 更低
            continue
        ok = True
        for m in range(1, k):
            m_bar, m_price = pl_queue[m]
            lp = line_price(B_bar, B_price, a_bar, a_price, m_bar)
            if m_price < lp:            # 中间低点跌破连线
                ok = False
                break
        if not ok:
            continue

        # 找 L: B-a 之间最高枢轴高点
        L_price, L_bar = highest_high_between(ph_queue, B_bar, a_bar)
        if L_bar < 0:
            continue

        dn_base = {'start': [B_bar, B_price], 'end': [a_bar, a_price], 'points': [[B_bar, B_price], [a_bar, a_price]]}

        # 类型1(下边界延长): B 回望更早低点, 共线
        for c_bar, c_price in pl_queue[k+1:]:
            if c_price >= B_price:
                continue
            ext = line_price(B_bar, B_price, a_bar, a_price, c_bar)
            if abs(c_price - ext) <= tol:
                record(drawn, seen, None, None, {
                    'start': [c_bar, c_price], 'end': [a_bar, a_price],
                    'points': [[c_bar, c_price], [B_bar, B_price], [a_bar, a_price]],
                })

        # 类型2(上边界构建): B 回望更早低点 c, 找 c-B 之间最高高点 d
        for c_bar, c_price in pl_queue[k+1:]:
            d_price, d_bar = highest_high_between(ph_queue, c_bar, B_bar)
            if d_bar < 0:
                continue
            up_ok = True
            for h_bar, h_price in ph_queue:
                if d_bar < h_bar < L_bar:
                    lp = line_price(d_bar, d_price, L_bar, L_price, h_bar)
                    if h_price > lp:    # 高点突破上边界
                        up_ok = False
                        break
            if not up_ok:
                continue

            up_dir = classify_up_dir(data, d_bar, d_price, L_bar, L_price)
            if up_dir == 'up':
                continue

            # 6.5 v3: 0.618 回调必要条件 (d -> B -> L -> a, 下降结构)
            fibo = fibo_ok_dn(d_price, B_price, L_price, a_price)
            if fibo is None:
                continue
            dn_base['fibo'] = {'r2': round(fibo[0], 4), 'r3': round(fibo[1], 4)}

            ttype = '对称三角' if up_dir == 'down' else '上升三角'

            up_points = [[d_bar, d_price], [L_bar, L_price]]
            up_start = [d_bar, d_price]
            for e_bar, e_price in ph_queue:
                if e_bar >= d_bar:
                    continue
                if up_dir == 'down':
                    ext = line_price(d_bar, d_price, L_bar, L_price, e_bar)
                    if abs(e_price - ext) <= tol and e_price > d_price:
                        up_points.insert(0, [e_bar, e_price])
                        up_start = [e_bar, e_price]
                else:  # flat
                    if high_shadow_overlap(data, e_bar, e_price, d_bar, d_price):
                        up_points.insert(0, [e_bar, e_price])
                        up_start = [e_bar, e_price]

            up_line = {'start': up_start, 'end': [L_bar, L_price], 'points': up_points}
            record(drawn, seen, ttype, up_line, dn_base)

# ====================================================================
# 9. 主循环
# ====================================================================

def detect(data, pivot_lookback=6, atr_period=14, atr_mult=1.0, queue_size=6):
    n = len(data)
    atr_arr = calc_atr(data, atr_period)
    highs, lows = detect_pivots(data, pivot_lookback)

    # 预索引: bar -> 是否枢轴点
    ph_set = {b: p for b, p in highs}
    pl_set = {b: p for b, p in lows}

    print(f"数据: {len(data)} 根 | {data[0]['date']} ~ {data[-1]['date']}")
    print(f"参数: pivot_lookback={pivot_lookback}, atr={atr_period}, atr_mult={atr_mult}, queue={queue_size}")
    print(f"枢轴点: 高点 {len(highs)} 个, 低点 {len(lows)} 个\n")

    ph_queue = []   # [(bar, price)], 最新在前
    pl_queue = []
    drawn = []      # 记录所有识别出的线
    seen = set()    # 去重

    for bar in range(n):
        atr_val = atr_arr[bar]
        if atr_val <= 0:
            continue
        tol = atr_mult * atr_val

        if bar in ph_set:
            ph_queue.insert(0, (bar, ph_set[bar]))
            if len(ph_queue) > queue_size:
                ph_queue.pop()
            if len(ph_queue) >= 2:
                handle_ph(ph_queue, pl_queue, data, atr_val, tol, drawn, seen)

        if bar in pl_set:
            pl_queue.insert(0, (bar, pl_set[bar]))
            if len(pl_queue) > queue_size:
                pl_queue.pop()
            if len(pl_queue) >= 2:
                handle_pl(pl_queue, ph_queue, data, atr_val, tol, drawn, seen)

    return drawn

# ====================================================================
# 10. 主程序
# ====================================================================

if __name__ == '__main__':
    data = fetch_data("历史数据/XRP_USD_1d_2023.csv")
    drawn = detect(data)

    print("=" * 70)
    print(f"共识别 {len(drawn)} 条线\n")

    for i, d in enumerate(drawn, 1):
        tt = d['triangle'] or '(延长线)'
        up = d['up']
        dn = d['dn']
        parts = [f"[{i:2d}] {tt}"]
        if up:
            pts = ' -> '.join(f"{data[p[0]]['date']}@{p[1]:.4f}" for p in up['points'])
            parts.append(f"  上边界({len(up['points'])}触点): {pts}")
        if dn:
            pts = ' -> '.join(f"{data[p[0]]['date']}@{p[1]:.4f}" for p in dn['points'])
            parts.append(f"  下边界({len(dn['points'])}触点): {pts}")
        print('\n'.join(parts))
        print()

    # 统计
    types = {}
    for d in drawn:
        if d['triangle']:
            types[d['triangle']] = types.get(d['triangle'], 0) + 1
    print("类型统计:", types)

    # 写 JSON
    out = {
        'params': {'symbol': 'XRPUSD', 'interval': '1d',
                   'pivot_lookback': 6, 'atr_period': 14, 'atr_mult': 1.0, 'queue_size': 6,
                   'v3_fibo': '>=0.618 x2'},
        'data_range': f"{data[0]['date']} ~ {data[-1]['date']}",
        'total_bars': len(data),
        'lines_found': len(drawn),
        'types': types,
        'lines': [
            {
                'triangle': d['triangle'],
                'fibo': (d['up']['fibo'] if d['up'] and 'fibo' in d['up']
                         else d['dn']['fibo'] if d['dn'] and 'fibo' in d['dn'] else None),
                'up': [{'bar': p[0], 'date': data[p[0]]['date'], 'price': round(p[1], 5)} for p in d['up']['points']] if d['up'] else None,
                'dn': [{'bar': p[0], 'date': data[p[0]]['date'], 'price': round(p[1], 5)} for p in d['dn']['points']] if d['dn'] else None,
            } for d in drawn
        ],
    }
    jp = 'D:/cursor/firstcc/_xrpusd_triangle_v3.json'
    with open(jp, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n结果已写入: {jp}")
