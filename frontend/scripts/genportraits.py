"""Génère les grilles de portraits en pixel art.

Chaque ligne est décrite par des paires (caractère, répétitions) : la largeur
est donc juste par construction, ce qui évite de compter des chaînes à la main.
"""

GRID = 16


def row(*pairs: tuple[str, int]) -> str:
    """Étend des paires en une ligne, en centrant le reste sur des points."""
    body = "".join(ch * n for ch, n in pairs)
    assert len(body) <= GRID, f"ligne trop large ({len(body)}): {body}"
    pad = GRID - len(body)
    left = pad // 2
    return "." * left + body + "." * (pad - left)


# Le visage occupe 8 colonnes, encadré par les cheveux.
def face(*pairs: tuple[str, int]) -> str:
    inner = "".join(ch * n for ch, n in pairs)
    assert len(inner) == 8, f"interieur du visage = {len(inner)}, attendu 8"
    return inner


# Yeux d'un seul pixel : à 16 px de côté, deux pixels lisent comme un masque.
EYES = face(("s", 2), ("e", 1), ("s", 2), ("e", 1), ("s", 2))
PLAIN = face(("s", 8))
NOSE = face(("s", 3), ("d", 2), ("s", 3))
MOUTH = face(("s", 2), ("m", 4), ("s", 2))
BROW = face(("s", 8))


def head_standard(eyes_row: str, brow_row: str = BROW) -> list[str]:
    """Tête de base, cheveux courts.

    Une ligne neutre sépare le nez de la bouche : collés, les deux se
    fondent en une seule tache sombre au milieu du visage.
    """
    h = "k"
    return [
        row(),
        row((h, 8)),
        row((h, 10)),
        row((h, 2), ("s", 6), (h, 2)),
        row((h, 1), (brow_row, 1), (h, 1)),
        row((h, 1), (eyes_row, 1), (h, 1)),
        row((h, 1), (PLAIN, 1), (h, 1)),
        row((h, 1), (NOSE, 1), (h, 1)),
        row((h, 1), (PLAIN, 1), (h, 1)),
        row((h, 1), (MOUTH, 1), (h, 1)),
        row(("s", 6)),
        row(("d", 4)),
    ]


# --- Atlas : lunettes. Deux montures encadrent chacune un œil, reliées par
# un pont de peau. Une barre pleine en travers du front lisait comme un
# bandeau, et teinter toute la rangée des yeux comme une visière.
GLASSES = face(("g", 1), ("e", 1), ("g", 1), ("s", 2), ("g", 1), ("e", 1), ("g", 1))
atlas = head_standard(GLASSES)

# --- Mentor : chignon haut, mèches longues sur les côtés ---
mentor = head_standard(EYES)
mentor[0] = row(("k", 4))
mentor[3] = row(("k", 3), ("s", 6), ("k", 3))
for i, inner in ((4, BROW), (5, EYES), (6, PLAIN), (7, NOSE), (8, PLAIN), (9, MOUTH)):
    mentor[i] = row(("k", 2), (inner, 1), ("k", 2))

# --- Vigie : casque. L'arceau passe au-dessus des cheveux pour relier les
# deux écouteurs, sinon ils flottent de part et d'autre de la tête.
vigie = head_standard(EYES)
vigie[2] = row(("g", 12))
vigie[3] = row(("g", 1), ("k", 2), ("s", 6), ("k", 2), ("g", 1))
for i, inner in ((4, BROW), (5, EYES), (6, PLAIN)):
    vigie[i] = row(("g", 1), ("k", 1), (inner, 1), ("k", 1), ("g", 1))

# --- Forge : casquette à visière ---
forge = head_standard(EYES)
forge[1] = row(("K", 10))
forge[2] = row(("K", 12))
forge[3] = row(("g", 12))

HEADS = {"finance": atlas, "revisions": mentor, "veille": vigie, "code": forge}

for name, rows in HEADS.items():
    assert len(rows) == 12, f"{name}: {len(rows)} lignes"
    for i, r in enumerate(rows):
        assert len(r) == GRID, f"{name} ligne {i}: {len(r)} caracteres -> {r}"

import pathlib
import re

TARGET = pathlib.Path(__file__).resolve().parent.parent / "src" / "portraits.ts"

src = TARGET.read_text()
for name, rows in HEADS.items():
    body = "\n".join(f'      "{r}",' for r in rows)
    pattern = re.compile(
        r"(\b" + name + r": \{\s*\n\s*head: \[\n)(.*?)(\n    \],)", re.S
    )
    assert pattern.search(src), f"bloc introuvable : {name}"
    src = pattern.sub(lambda m: m.group(1) + body + m.group(3), src, count=1)

TARGET.write_text(src)

for name, rows in HEADS.items():
    print(f"  {name}")
    for r in rows:
        print(f"    {r}")

print("\nOK — 4 tetes x 12 lignes x 16 caracteres, portraits.ts mis a jour")
