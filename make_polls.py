"""Rebuild polls.json and static/art/ from the poll document and the deck artwork.
usage: python3 make_polls.py POLLS_MD ART_DIR
POLLS_MD holds "## Poll N: Title (slide N)" headings, a "**Question:**" line, and "- option" lines.
ART_DIR holds the source images named in PANELS."""
import json, re, sys
from pathlib import Path
from PIL import Image

DOC, ART = Path(sys.argv[1]), Path(sys.argv[2])
# One panel per poll, in poll order: (source image, alt text).
PANELS = [
    ("refs/slide-05.jpg", "A red streetcar speeds toward five people on the tracks."),
    ("refs/slide-17.jpg", "A self-driving car faces three paths: an elderly pedestrian, a barrier, and a child."),
    ("refs/slide-29.jpg", "A robot hand pulls one resume from a mountain of applications."),
    ("art/4.05.jpg", "Students in a school hallway; several girls stand apart while others whisper over phones."),
    ("art/5.08.jpg", "Five contestants at podiums: model maker, app developer, your employer, the website, and you."),
    ("art/6.03.jpg", "A teenager on a school bus at dusk smiles at a chat on her phone."),
    ("refs/slide-81.jpg", "A trolley labeled AI detection policy heads toward actual cheaters on one track and falsely accused students on the other."),
    ("refs/slide-72.jpg", "A student types at a laptop at 2 AM, surrounded by coffee cups and notes."),
    ("refs/slide-88.jpg", "Six figures stand in a row: technologist, policy maker, philosopher, journalist, business leader, and an unknown future."),
]

polls, cur = [], None
for line in DOC.read_text().splitlines():
    m = re.match(r"## (.+?) \(slide (\d+)\)$", line)
    if m:
        cur = {"id": f"p{len(polls) + 1}", "title": m.group(1), "slide": int(m.group(2)), "question": "", "options": []}
        polls.append(cur)
    elif cur and line.startswith("**Question:**"):
        cur["question"] = line.split("**Question:**", 1)[1].strip()
    elif cur and line.startswith("- "):
        cur["options"].append(line[2:].strip())
assert len(polls) == len(PANELS), (len(polls), len(PANELS))

for p, (src, alt) in zip(polls, PANELS):
    Image.open(ART / src).convert("RGB").resize((960, 536), Image.LANCZOS).save(f"static/art/{p['id']}.jpg", quality=80, optimize=True)
    p.update(image=f"/art/{p['id']}.jpg", alt=alt)
Path("polls.json").write_text(json.dumps(polls, indent=1, ensure_ascii=False))
for p in polls:
    print(p["id"], p["slide"], p["title"])
