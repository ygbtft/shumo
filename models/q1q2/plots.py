"""Render saved numerical/analytic payloads only; plotting never invokes a solver."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import csv
import json
import numpy as np


@dataclass(frozen=True)
class PlotStyle:
    font_family: str = 'Noto Sans CJK SC'
    dpi: int = 180
    figsize: tuple[float, float] = (9., 7.)


@dataclass(frozen=True)
class ResultBundle:
    figures: tuple[dict, ...] = ()
    tables: dict[str, list[dict]] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


def _geometry(ax, panel):
    from matplotlib.patches import Circle, Polygon
    for polygon in panel.get('polygons', ()):
        points = np.asarray(polygon['vertices'])
        if len(points) >= 3:
            ax.add_patch(Polygon(points, closed=True, fill=polygon.get('fill', False), alpha=.35,
                                 edgecolor=polygon.get('color', 'C0'), facecolor=polygon.get('color', 'C0'),
                                 label=polygon.get('label')))
        elif len(points):
            ax.plot(points[:, 0], points[:, 1], 'o-', label=polygon.get('label'))
    for group in panel.get('points', ()):
        points = np.asarray(group['values']).reshape(-1, 2)
        if len(points):
            ax.scatter(points[:, 0], points[:, 1], s=group.get('size', 9),
                       facecolors='none' if group.get('open', False) else group.get('color', 'C0'),
                       edgecolors=group.get('color', 'C0'), label=group.get('label'))
    for line in panel.get('lines', ()):
        p = np.asarray(line['values'])
        ax.plot(p[:, 0], p[:, 1], line.get('style', '-'), color=line.get('color'), label=line.get('label'))
    for circle in panel.get('circles', ()):
        if circle.get('radius') is not None:
            ax.add_patch(Circle(circle['center'], circle['radius'], fill=False,
                                linestyle=circle.get('style', '--'), edgecolor=circle.get('color', 'C1'),
                                label=circle.get('label')))
    for arrow in panel.get('arrows', ()):
        ax.annotate('', xy=arrow['end'], xytext=arrow['start'], arrowprops={'arrowstyle': '->'})
    ax.autoscale_view()
    if 'limits' in panel:
        x0, x1, y0, y1 = panel['limits']
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
    ax.set_aspect('equal', adjustable='box')
    ax.set_xlabel('x / m')
    ax.set_ylabel('y / m')


def render(results: ResultBundle, output_dir: Path, style: PlotStyle) -> tuple[Path, ...]:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font = font_manager.findfont(style.font_family, fallback_to_default=True)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    files = []
    with plt.rc_context({'font.family': style.font_family, 'axes.unicode_minus': False}):
        for spec in results.figures:
            panels = spec.get('panels', (spec,))
            fig, axes = plt.subplots(1, len(panels), figsize=(style.figsize[0]*len(panels), style.figsize[1]), squeeze=False)
            try:
                for ax, panel in zip(axes[0], panels):
                    kind = panel.get('kind', 'geometry')
                    if kind == 'geometry':
                        _geometry(ax, panel)
                    elif kind == 'heatmap':
                        # OUT and unassessed cells retain distinct colours, never a zero score.
                        rows = panel['records']
                        out = np.array([r['q'] for r in rows if r['status'] == 'OUT']).reshape(-1, 2)
                        pending = np.array([r['q'] for r in rows if r['status'] == 'NOT_EVALUATED']).reshape(-1, 2)
                        if len(out):
                            ax.scatter(out[:, 0], out[:, 1], c='lightgrey', marker='s', s=4, label='不可行')
                        if len(pending):
                            ax.scatter(pending[:, 0], pending[:, 1], c='white', edgecolor='grey', marker='s', s=5, label='未评估')
                        valid = [r for r in rows if r.get('diameter_estimate_m') is not None]
                        if valid:
                            p = np.array([r['q'] for r in valid])
                            artist = ax.scatter(p[:, 0], p[:, 1], c=[r['diameter_estimate_m'] for r in valid], s=9, marker='s')
                            fig.colorbar(artist, ax=ax, label='最坏物理后验直径样本估计 / m')
                        _geometry(ax, panel)
                    elif kind == 'curve':
                        for series in panel.get('series', ()):
                            ax.plot(series['x'], series['y'], series.get('style', 'o-'), label=series.get('label'))
                            if series.get('low') is not None:
                                ax.fill_between(series['x'], series['low'], series['high'], alpha=.2)
                        ax.set_xlabel(panel.get('xlabel', ''))
                        ax.set_ylabel(panel.get('ylabel', ''))
                    elif kind == 'bars':
                        ax.bar(panel['labels'], panel['values'])
                        ax.tick_params(axis='x', rotation=25)
                        ax.set_ylabel(panel.get('ylabel', ''))
                    else:
                        raise ValueError(f'unknown saved figure kind: {kind}')
                    ax.set_title(panel.get('title', ''))
                    if ax.get_legend_handles_labels()[0]:
                        ax.legend(fontsize='small')
                    ax.grid(alpha=.2)
                fig.suptitle(spec.get('caption', ''))
                fig.tight_layout()
                for suffix in ('pdf', 'png'):
                    path = output_dir/f"{spec['id']}.{suffix}"
                    fig.savefig(path, dpi=style.dpi, bbox_inches='tight')
                    files.append(path)
            finally:
                plt.close(fig)
        for name, rows in results.tables.items():
            path = output_dir/f'{name}.csv'
            keys = list(dict.fromkeys(key for row in rows for key in row))
            with path.open('w', newline='', encoding='utf-8-sig') as stream:
                writer = csv.DictWriter(stream, fieldnames=keys)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list, tuple)) else v
                                     for k, v in row.items()})
            files.append(path)
    log = output_dir/'plot_manifest.json'
    log.write_text(json.dumps({'requested_font': style.font_family, 'resolved_font_file': font,
                               'metadata': results.metadata, 'files': [p.name for p in files]}, ensure_ascii=False, indent=2), encoding='utf-8')
    return tuple(files+[log])
