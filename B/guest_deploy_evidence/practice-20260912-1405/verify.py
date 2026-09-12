import json,hashlib,pathlib
r=pathlib.Path.cwd()
d=json.loads((r/'DEPLOY_MANIFEST.json').read_text())
bad=[n for n,v in d.items() if not (r/n).exists() or hashlib.sha256((r/n).read_bytes()).hexdigest()!=v['sha256']]
print('verified',len(d),'files; mismatches:',bad)
if bad: raise SystemExit(1)
