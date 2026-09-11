"""Independently verify every rejected 21-site layout against a legal source."""
import json
from pathlib import Path
import numpy as np
from multicore_cover_search import points
from peer_benchmark import PeerTransport  # Initialize the read-only peer import path.
from mock.scenario_gen import Source
from mock.geometry import covered

ROOT = Path(__file__).resolve().parent


def main():
    for name, expected in (("multicore-cover-search", 216), ("multicore-cover-smallcore", 192)):
        out = ROOT / "experiments/runs" / f"2026-09-11_{name}"
        if (out / "witness_verification.json").exists():
            raise RuntimeError("Preserving independent geometry audit")
        rows = [json.loads(line) for line in (out / "search_log.jsonl").read_text().splitlines()]
        assert len(rows) == expected
        checks = []
        for row in rows:
            w = row["sample_witness"]
            assert w is not None and not row["certified"] and "unresolved_certificate" not in row
            g = np.array(w["position"])
            assert np.linalg.norm(g) <= 1800. + 1e-8
            p = points(row["spec"])
            angle = np.radians(w["direction_deg"])
            normal = np.array([np.cos(angle), np.sin(angle)])
            received = (np.linalg.norm(p-g, axis=1) <= 1000.) & ((p-g) @ normal >= 0.)
            assert not received.any(), row["index"]
            source = Source(1, float(g[0]), float(g[1]), 1000., w["direction_deg"])
            assert all(not covered(source, tuple(q)) for q in p)
            checks.append(dict(index=row["index"], passed=True, witness=w,
                               independent_dot_product_receivers=0, backend_receivers=0))
        (out / "witness_verification.json").write_text(json.dumps(dict(passed=len(checks), failed=0, checks=checks,
            implication="Each tested layout has an admissible source missed by all 21 stations; append nine other legal distinct-channel sources to make a full scene",
            scored_execution_count=0, official_calls=0), indent=2))
        (out / "summary.md").write_text(f"# 21站多内核候选被反例拒绝\n\n本批{expected}个冻结参数组合全部找到真实漏检源，0个通过、0个仅因证书未决而拒绝。独立点积/距离和本地后端两种判定均验证：接收半径1000m、闭合180度的合法源对21个站都无信号。可补充9个不同频道合法源组成题设完整场景，仍至少漏掉该见证源。\n\n每个参数及源坐标/朝向保存在search_log.jsonl，独立核查在witness_verification.json。这只否定这批候选，不证明所有21站布局不可能。没有策略计分执行；不以采样通过冒充连续覆盖证明。\n")
        (out / "next_steps.md").write_text("# 后续\n\n不把本批21站布局用于保证扫描，保留已认证22站。后续可尝试非对称位置或不同内中外数量分配，但任何候选须先得到连续覆盖证书与独立分区核验，再进入策略训练。408个反例不构成21站下界证明。\n")
        print(name, len(checks), "actual blind-source witnesses passed")


if __name__ == "__main__":
    main()
