import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]);records=json.loads((root/'manifest.json').read_text())
bad=[name for name,digest in records.items() if not (root/name).is_file() or hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest]
assert not bad,bad
print('Verified frozen formal package:',len(records),'files')
