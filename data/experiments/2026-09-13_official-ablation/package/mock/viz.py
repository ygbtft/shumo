"""Offline truth visualization, never provided to a strategy."""
import argparse
import json
import os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR', str(Path(__file__).parent/'.mplconfig'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Wedge
import numpy as np


def plot_case(case, output, coverage=False):
    fig, ax = plt.subplots(figsize=(10, 9), layout='constrained')
    ax.add_patch(Circle((0,0), 1800, fill=False, color='#3f5367', linewidth=1.5, label='Arena (1800 m)'))
    points = np.asarray([item['position'] for item in case.get('trace', [])])
    if len(points): ax.plot(points[:,0], points[:,1], color='#518bb2', alpha=.5, lw=.7, label='Dog path')
    success = [t for t in case.get('trace', []) if t['response'].get('clear_result') == 'success']
    cleared = {t['request']['channel'] for t in success}
    for source in case['scenario']['sources']:
        x, y = source['x'], source['y']
        direction = source['direction_deg']
        color = '#159570' if source['channel'] in cleared else '#d23c48'
        ax.scatter(x, y, c=color, marker='o' if direction is None else '^', s=45, zorder=4)
        ax.annotate(str(source['channel']), (x,y), xytext=(5,5), textcoords='offset points', fontsize=8)
        if direction is not None:
            theta = np.deg2rad(direction)
            ax.arrow(x,y,130*np.cos(theta),130*np.sin(theta), color=color, head_width=28, length_includes_head=True)
        if coverage:
            patch = Circle((x,y), source['radius']) if direction is None else Wedge((x,y),source['radius'],direction-90,direction+90)
            patch.set(color=color, alpha=.055); ax.add_patch(patch)
    if success:
        xy = np.asarray([t['position'] for t in success])
        ax.scatter(xy[:,0], xy[:,1], c='#e6a126', marker='x', s=60, linewidths=1.7, label='Successful clear position', zorder=5)
    ax.scatter([0],[0], c='#192738', marker='*', s=100, label='Start', zorder=6)
    # Legend conveys all true-source states even when one category is absent.
    ax.scatter([],[], c='#159570', marker='o', label='Cleared source (circle=omni)')
    ax.scatter([],[], c='#d23c48', marker='^', label='Uncleared source (triangle=directional)')
    m = case.get('metrics', {})
    detail = f"{len(cleared)}/{len(case['scenario']['sources'])} cleared"
    if m.get('average_clear_time_s') is not None: detail += f" | {m['average_clear_time_s']:.1f} s/source"
    ax.set(title=f"Local mock — seed {case['scenario']['seed']}\n{detail}", xlabel='East x (m)', ylabel='North y (m)', aspect='equal')
    ax.grid(alpha=.18); ax.legend(loc='upper left', fontsize=8)
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160); plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('case')
    p.add_argument('--output', default='mock/results/trajectory.png')
    p.add_argument('--coverage', action='store_true')
    args = p.parse_args()
    plot_case(json.loads(Path(args.case).read_text(encoding='utf-8')), args.output, args.coverage)
    print(args.output)

if __name__ == '__main__': main()
