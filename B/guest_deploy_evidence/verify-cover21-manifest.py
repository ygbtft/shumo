import hashlib,json,pathlib
root=pathlib.Path(r"C:\BRobot")
m=json.loads((root/"DEPLOY_MANIFEST.json").read_text())
for item in m["files"]:
    p=root/item["path"]
    assert hashlib.sha256(p.read_bytes()).hexdigest()==item["sha256"],str(p)
print("Verified",len(m["files"]),"runtime files by SHA256")
