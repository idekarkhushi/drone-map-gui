from pathlib import Path

root = Path('Updated GUI')
repls = [
    ('"Times New Roman"', '"Good Times"'),
    ("'Times New Roman'", "'Good Times'"),
    ('"Courier New"', '"Good Times"'),
    ("'Courier New'", "'Good Times'"),
    ('FONT     = "Times New Roman"', 'FONT     = "Good Times"'),
    ('font=("Times New Roman"', 'font=("Good Times"'),
]

changed = []
for path in root.rglob('*.py'):
    text = path.read_text(encoding='utf-8')
    new = text
    for old, new_s in repls:
        new = new.replace(old, new_s)
    if new != text:
        path.write_text(new, encoding='utf-8')
        changed.append(str(path))

print('CHANGED', len(changed))
for p in changed[:50]:
    print(p)
