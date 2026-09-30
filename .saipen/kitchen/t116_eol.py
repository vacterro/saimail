"""Restore per-line EOLs lost by a text-mode rewrite: lines equal to a reference keep its ending."""
import difflib
import hashlib
import sys
from pathlib import Path


def split(b):
    parts = b.split(b'\n')
    lines = [(p[:-1], b'\r\n') if p.endswith(b'\r') else (p, b'\n') for p in parts[:-1]]
    return lines, parts[-1]


def rebuild(ref_bytes, cur_text, new_eol):
    ref, _ = split(ref_bytes)
    cur = cur_text.split('\n')
    tail = cur.pop() if not cur_text.endswith('\n') else None
    if tail is None:
        cur = cur_text.split('\n')[:-1]
    cur_b = [c.encode('utf-8') for c in cur]
    sm = difflib.SequenceMatcher(None, [r[0] for r in ref], cur_b, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        for k in range(j2 - j1):
            if tag == 'equal':
                out.append(cur_b[j1 + k] + ref[i1 + k][1])
            else:
                eol = new_eol(ref, i1, i2, k) if callable(new_eol) else new_eol
                out.append(cur_b[j1 + k] + eol)
    data = b''.join(out)
    if tail:
        data += tail.encode('utf-8')
    return data


if __name__ == '__main__':
    ref, target = sys.argv[1], sys.argv[2]
    text = Path(target).read_bytes().decode('utf-8').replace('\r\n', '\n')
    data = rebuild(Path(ref).read_bytes(), text, lambda r, i1, i2, k: r[min(i1, len(r) - 1)][1])
    Path(target).write_bytes(data)
    print(hashlib.sha256(data).hexdigest())
