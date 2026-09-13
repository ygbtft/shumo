"""Audit saved official formal responses without sending simulator requests."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CASE = 'G4MK-ZVXM-A682-MVBS'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    case_dir = ROOT / 'results' / CASE
    run, = case_dir.glob('*-bounded-formal')
    summary = read(run / 'summary.json')
    events = [json.loads(s) for s in (run / 'requests.jsonl').read_text().splitlines()]
    assert summary['mode'] == 'formal' and summary['case_code'] == CASE
    assert summary['status'] == 'policy-completed' and summary['mock_executions'] == 0
    assert summary['parameters'] == dict(task_order='nearest', trial_radius=65., max_active=2,
        share_limit=6, localization_weight=.08, remainder_weight=1.5)
    counts = Counter()
    position, channel, virtual, distance, max_error = (0., 0.), 1, 0., 0., 0.
    ids = set()
    for e in events:
        assert 'event' not in e, 'Transport failure requires separate reconciliation'
        q, r, path = e['request'], e['response'], e['path']
        assert e['http_status'] == 200 and r['accepted'] is True
        assert q['request_id'] not in ids
        ids.add(q['request_id'])
        counts[path] += 1
        cost = 0.
        if path in ('/measure', '/clear'):
            point = (q['position']['x'], q['position']['y'])
            movement = math.dist(position, point)
            distance += movement
            cost += movement / 5
            position = point
        if path == '/measure':
            switched = int(q['channel'] != channel)
            counts['switches'] += switched
            channel = q['channel']
            cost += 5 + switched
        if path == '/clear':
            success = r['clear_result'] == 'success'
            counts['cleared'] += int(success)
            counts['failed_clears'] += int(not success)
            cost += 5 if success else 3
        max_error = max(max_error, abs(r['virtual_time_s'] - virtual - cost))
        virtual = r['virtual_time_s']
    assert events[0]['path'] == '/enter' and events[-1]['path'] == '/exit'
    assert counts['/enter'] == counts['/exit'] == 1
    assert events[-1]['response']['exit_reason'] == 'user_exit'
    assert max_error < 2e-6
    assert virtual == summary['total_virtual_s'] and counts['cleared'] == summary['cleared']
    assert len(events) == summary['official_calls']
    meta = read(case_dir / f'formal-p3-3-{CASE}.result.json')
    upload, = read(ROOT / 'formal-upload-snapshot/rows.json')['rows']
    jlog = case_dir / f'formal-p3-3-{CASE}.jlog'
    digest = hashlib.sha256(jlog.read_bytes()).hexdigest()
    assert digest == meta['package_sha256'] == upload['package_sha256']
    assert jlog.stat().st_size == upload['package_bytes']
    assert meta['problem_no'] == upload['problem_no'] == 3
    assert meta['formal_index'] == upload['formal_index'] == 3
    assert meta['case_code'] == upload['case_code'] == CASE
    assert upload['state'] == 'confirmed' and upload['formal_upload_state'] == 'outer_verified'
    ui = read(ROOT / 'ui-evidence/007-6-view-upload/003-formal-upload-history.uia.json')
    names = [r['text'] for r in ui]
    assert CASE in names and '已用3次，剩余0次（共3次）' in names and '已上传' in names
    result = dict(case_code=CASE, formal_index=3, cleared=counts['cleared'],
        failed_clears=counts['failed_clears'], total_virtual_s=virtual,
        seconds_per_cleared_source=virtual/counts['cleared'], program_runtime_s=summary['wall_s'],
        official_total_source_count=None, official_score=None, counts=dict(counts),
        distance_m=distance, max_action_ledger_error_s=max_error,
        all_requests_accepted=True, single_enter_and_exit=True, uploaded=True,
        official_jlog_sha256=digest, parameters=summary['parameters'])
    (ROOT / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
