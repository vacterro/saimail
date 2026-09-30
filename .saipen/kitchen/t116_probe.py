import re
import pathlib
PAT = re.compile(
    r"\bT-\d+ (?:still )?owns\b|"
    r"\bowns? (?:the )?(?:subsequent|that|next) continuation|"
    r"\bT-\d+ (?:is|remains) (?:still )?(?:the )?(?:active|current)\b|"
    r"\b(?:the )?current (?:capability[- ]truth |capability/recovery truth |truth )?repair\b|"
    r"\b(?:inside|in|outside|part of) this repair\b|"
    r"\bafter\b[^.;]{0,80}?\bis accepted\b",
    re.IGNORECASE)
root = pathlib.Path('.')
files = list(root.glob('humbox/*.md')) + list(root.glob('README*.md')) + list(root.glob('spec/*.md')) + [root/'lab/LATEST.md', root/'CHANGELOG.md', root/'.saipen/kitchen/T-113-reread-continuation.md']
for f in files:
    for para in f.read_text(encoding='utf-8').split('\n\n'):
        flat = ' '.join(para.replace('*','').replace('`','').split())
        for m in PAT.finditer(flat):
            print(f, '::', flat[max(0,m.start()-60):m.end()+40])
