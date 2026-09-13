"""Reproduce document text/table/OMML extraction. Output stays in mock/materials."""
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as E
import hashlib
import json

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
M='{http://schemas.openxmlformats.org/officeDocument/2006/math}'


def render(e):
    if e.tag in (W+'t',M+'t'): return e.text or ''
    if e.tag==W+'br': return '\n'
    if e.tag==W+'tab': return '\t'
    if e.tag==M+'f': return '('+render(e.find(M+'num'))+')/('+render(e.find(M+'den'))+')'
    if e.tag==M+'sSup': return render(e.find(M+'e'))+'^('+render(e.find(M+'sup'))+')'
    if e.tag==M+'sSub': return render(e.find(M+'e'))+'_('+render(e.find(M+'sub'))+')'
    return ''.join(render(c) for c in e)


def main():
    manifest={}
    for path in sorted((ROOT/'附件').glob('*.docx')):
        with ZipFile(path) as z: xml=z.read('word/document.xml')
        root=E.fromstring(xml);lines=[]
        for e in root.find(W+'body'):
            if e.tag==W+'tbl':
                lines+=['[TABLE]']+[' | '.join(render(c) for c in r.findall(W+'tc')) for r in e.findall(W+'tr')]+['[/TABLE]']
            else: lines.append(render(e))
        (OUT/(path.stem+'.txt')).write_text('\n'.join(lines),encoding='utf-8')
        (OUT/(path.stem+'.xml')).write_bytes(xml)
        formulas=list(root.iter(M+'oMath'))
        (OUT/(path.stem+'-formulas.txt')).write_text('\n'.join(render(e) for e in formulas),encoding='utf-8')
        manifest[path.name]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'tables':len(list(root.iter(W+'tbl'))),'formulas':len(formulas)}
    import pymupdf
    path=ROOT/'B题.pdf';doc=pymupdf.open(path)
    (OUT/'题面.txt').write_text('\n'.join(f'=== PAGE {i+1} ===\n'+p.get_text() for i,p in enumerate(doc)),encoding='utf-8')
    for i,p in enumerate(doc): p.get_pixmap(matrix=pymupdf.Matrix(1.25,1.25)).save(OUT/f'题面-{i+1}.png')
    manifest[path.name]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'pages':len(doc)}
    handoff=ROOT/'ENV-HANDOFF.md'
    manifest[handoff.name]={'sha256':hashlib.sha256(handoff.read_bytes()).hexdigest(),'read_completely':True}
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()
