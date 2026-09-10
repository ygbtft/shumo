from pathlib import Path
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT = Path(__file__).resolve().parents[1]


def main():
    template = (PROJECT / "paper/manuscript_template.md").read_text(encoding="utf-8")
    destination = PROJECT / "paper/equations"
    destination.mkdir(parents=True, exist_ok=True)
    equations = re.findall(r"\[\[EQ:(\d+)\|(.+)\]\]", template)
    plt.rcParams.update({"mathtext.fontset": "stix", "font.family": "STIXGeneral"})
    for number, expression in equations:
        figure = plt.figure(figsize=(10, 0.85))
        figure.text(0.01, 0.5, "$" + expression + "$", fontsize=15, va="center")
        figure.savefig(destination / f"equation_{number}.png", dpi=240, bbox_inches="tight", pad_inches=0.035, transparent=False)
        plt.close(figure)
    print(f"Rendered {len(equations)} equations", flush=True)


if __name__ == "__main__":
    main()
