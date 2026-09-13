"""Lossless archive of bulky raw searches plus readable compact report inputs."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
folder=Path(sys.argv[1])
for path in folder.glob('*.json'):
    data=json.loads(path.read_text())
    if 'search' not in data or 'raw_search_archive' in data:
        continue
    raw=path.read_bytes()
    archive=path.with_suffix('.full.json.gz')
    if archive.exists():
        raise FileExistsError(archive)
    with gzip.GzipFile(filename=str(archive),mode='wb',mtime=0) as f:
        f.write(raw)
    data['raw_search_archive']=dict(path=archive.name,sha256_uncompressed=hashlib.sha256(raw).hexdigest(),
        note='lossless full original record; readable JSON omits alternative pair witnesses only')
    for candidate in data['search']['alternatives']:
        sc=candidate['score']
        candidate['score']={k:sc[k] for k in ('J_hat','near_score_m','direction_score_m','sample_count','status')}
    path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n')
print('lossless raw archives and compact readable records saved')
