"""画 v2 vs v3 三角识别结果对比"""
import json, csv, os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

BASE = os.path.dirname(os.path.abspath(__file__))

def load_data(csv_path="历史数据/XRP_USD_1d_2023.csv"):
    data = []
    with open(os.path.join(BASE, csv_path), 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            data.append({
                'date': datetime.strptime(row['Date'], '%Y-%m-%d'),
                'close': float(row['Close']),
            })
    return data

COLORS = {'上升三角': '#26a69a', '下降三角': '#ef5350', '对称三角': '#ffa726'}

def draw(ax, data, result, title):
    dates = [d['date'] for d in data]
    closes = [d['close'] for d in data]
    ax.plot(dates, closes, color='#888888', linewidth=0.8, zorder=1)
    for line in result['lines']:
        tt = line['triangle']
        color = COLORS.get(tt, '#999999')
        alpha = 1.0 if tt else 0.55
        lw = 1.6 if tt else 1.0
        for side in ('up', 'dn'):
            pts = line[side]
            if not pts:
                continue
            xs = [data[p['bar']]['date'] for p in pts]
            ys = [p['price'] for p in pts]
            ax.plot(xs, ys, color=color, linewidth=lw, alpha=alpha, zorder=2)
            ax.scatter(xs, ys, s=12, color=color, alpha=alpha, zorder=3)
    ax.set_title(title)
    ax.set_ylabel('价格 (USD)')
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    plt.setp(ax.get_xticklabels(), rotation=45)

def main():
    data = load_data()
    v2 = json.load(open(os.path.join(BASE, '_xrpusd_triangle_v2.json'), encoding='utf-8'))
    v3 = json.load(open(os.path.join(BASE, '_xrpusd_triangle_v3.json'), encoding='utf-8'))

    fig, axes = plt.subplots(2, 1, figsize=(22, 14))
    draw(axes[0], data, v2, f"v2: 三角形 {sum(v2['types'].values())} 个 (对称{ v2['types'].get('对称三角',0)} / 上升{v2['types'].get('上升三角',0)} / 下降{v2['types'].get('下降三角',0)})")
    draw(axes[1], data, v3, f"v3 (+0.618回调过滤): 三角形 {sum(v3['types'].values())} 个 (对称{v3['types'].get('对称三角',0)} / 上升{v3['types'].get('上升三角',0)} / 下降{v3['types'].get('下降三角',0)})")

    from matplotlib.lines import Line2D
    handles = [Line2D([0], [0], color=c, lw=2, label=t) for t, c in COLORS.items()]
    handles.append(Line2D([0], [0], color='#999999', lw=1, alpha=0.55, label='延长线'))
    axes[0].legend(handles=handles, loc='upper left')

    plt.tight_layout()
    out = os.path.join(BASE, '_xrpusd_triangle_v2_vs_v3.png')
    plt.savefig(out, dpi=100)
    print(f"已保存: {out}")

if __name__ == '__main__':
    main()
