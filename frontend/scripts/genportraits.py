"""Génère les portraits pixel art des agents et réécrit src/portraits.ts.

Grille 32 × 32, buste cadré aux épaules. À cette largeur, écrire les lignes
à la main est ingérable : on peint sur un canevas, et les dimensions sont
donc justes par construction.

Deux états par agent :
  - civil   : vêtement neutre, propre à chaque personne
  - tenue   : combinaison bleue commune + baudrier à la couleur de l'agent,
              de son épaule gauche vers sa hanche droite

Lancement :  python3 scripts/genportraits.py
"""

from __future__ import annotations

import pathlib

W = H = 32

# --- Couleurs partagées -------------------------------------------------
SHARED = {
    "e": "#141019",  # pupille
    "w": "#f6f8ff",  # blanc de l'œil / insigne
    "u": "#2f5d99",  # combinaison, bleu commun
    "U": "#3f76bb",  # combinaison, zone éclairée
    "V": "#1f4272",  # combinaison, ombre
}


class Canvas:
    def __init__(self) -> None:
        self.px = [["." for _ in range(W)] for _ in range(H)]

    def set(self, x: int, y: int, ch: str) -> None:
        if 0 <= x < W and 0 <= y < H:
            self.px[y][x] = ch

    def box(self, x0: int, y0: int, x1: int, y1: int, ch: str) -> None:
        """Rectangle plein, bornes incluses."""
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.set(x, y, ch)

    def row_span(self, y: int, x0: int, x1: int, ch: str) -> None:
        self.box(x0, y, x1, y, ch)

    def rows(self) -> list[str]:
        return ["".join(r) for r in self.px]


# --- Silhouette du buste ------------------------------------------------
# Largeur des épaules par ligne : le buste s'évase vers le bas.
TORSO = {
    23: (11, 20),
    24: (9, 22),
    25: (7, 24),
    26: (6, 25),
    27: (5, 26),
    28: (4, 27),
    29: (4, 27),
    30: (3, 28),
    31: (3, 28),
}


def draw_head(c: Canvas, hair: str = "k") -> None:
    """Tête commune : crâne, visage, traits, cou.

    Les angles du crâne et de la mâchoire sont rognés d'un pixel : un
    rectangle plein donne une tête en brique.
    """
    # Chevelure (calotte), coins supérieurs rognés
    c.box(11, 3, 20, 3, hair)
    c.box(10, 4, 21, 5, hair)
    c.box(9, 6, 22, 7, hair)

    # Visage
    c.box(9, 8, 22, 18, "s")

    # Mèches sur les tempes. Elles s'arrêtent au-dessus de la ligne des
    # sourcils : descendues plus bas, cheveux et sourcils se rejoignent en
    # un bandeau continu en travers du front.
    c.box(9, 8, 10, 9, hair)
    c.box(21, 8, 22, 9, hair)

    # Oreilles
    c.box(8, 12, 8, 14, "s")
    c.box(23, 12, 23, 14, "s")

    # Sourcils
    c.row_span(10, 11, 13, hair)
    c.row_span(10, 18, 20, hair)

    # Yeux : blanc puis pupille, pour qu'ils lisent à distance.
    # Écartés pour laisser passer un pont de lunettes entre les deux.
    c.box(11, 12, 13, 13, "w")
    c.box(18, 12, 20, 13, "w")
    c.box(12, 12, 12, 13, "e")
    c.box(19, 12, 19, 13, "e")

    # Nez
    c.box(15, 14, 16, 16, "d")

    # Bouche
    c.row_span(18, 13, 18, "m")

    # Mâchoire qui se resserre, puis cou
    c.box(10, 19, 21, 19, "s")
    c.box(11, 20, 20, 20, "s")
    c.box(12, 21, 19, 21, "d")
    c.box(13, 22, 18, 22, "d")


def draw_torso(c: Canvas, base: str) -> None:
    for y, (x0, x1) in TORSO.items():
        c.row_span(y, x0, x1, base)


def draw_collar(c: Canvas, base: str, light: str) -> None:
    """Encolure : une échancrure claire autour du cou."""
    c.row_span(23, 13, 18, light)
    c.row_span(24, 12, 19, light)
    c.box(14, 23, 17, 24, base)


def draw_sash(c: Canvas, accent: str, edge: str) -> None:
    """Baudrier en diagonale, épaule gauche du personnage → hanche droite.

    Le personnage nous fait face : son épaule gauche est donc à droite de
    l'image. La bande descend de haut-droite vers bas-gauche.
    """
    for y, (x0, x1) in TORSO.items():
        # 2 colonnes vers la gauche par ligne descendue.
        center = 25 - 2 * (y - 23)
        for x in range(center - 2, center + 2):
            if x0 <= x <= x1:
                c.set(x, y, accent)
        # Liseré plus clair sur le bord haut de la bande.
        for x in (center + 2,):
            if x0 <= x <= x1:
                c.set(x, y, edge)


def build(hair: str, accessorise=None) -> tuple[list[str], list[str]]:
    """Retourne (civil, tenue) pour une tête donnée."""
    civil = Canvas()
    draw_head(civil, hair)
    draw_torso(civil, "c")
    civil.row_span(23, 13, 18, "v")
    civil.row_span(24, 12, 19, "v")
    if accessorise:
        accessorise(civil)

    uniform = Canvas()
    draw_head(uniform, hair)
    draw_torso(uniform, "u")
    draw_sash(uniform, "a", "A")
    draw_collar(uniform, "u", "U")
    if accessorise:
        accessorise(uniform)

    return civil.rows(), uniform.rows()


# --- Accessoires par agent ---------------------------------------------


def glasses(c: Canvas) -> None:
    """Atlas : deux verres distincts, séparés par un pont.

    Les verres doivent rester écartés : collés, les deux montures fusionnent
    en un seul bandeau et la tête porte des lunettes de soudeur.
    """
    for x0, x1 in ((10, 14), (17, 21)):
        c.row_span(11, x0, x1, "g")  # bord haut
        c.row_span(14, x0, x1, "g")  # bord bas
        c.box(x0, 12, x0, 13, "g")  # branche interne
        c.box(x1, 12, x1, 13, "g")  # branche externe
    c.row_span(12, 15, 16, "g")  # pont
    c.box(8, 12, 9, 12, "g")  # branches vers les oreilles
    c.box(22, 12, 23, 12, "g")


def bun(c: Canvas) -> None:
    """Mentor : chignon haut et mèches longues."""
    c.box(13, 1, 18, 3, "k")
    c.box(7, 8, 8, 20, "k")
    c.box(23, 8, 24, 20, "k")


def headset(c: Canvas) -> None:
    """Vigie : arceau fin et écouteurs compacts.

    Volontairement discret : un arceau épais et des écouteurs de trois
    pixels de large mangeaient la moitié du visage.
    """
    c.box(10, 2, 21, 2, "g")  # arceau
    c.box(8, 3, 9, 5, "g")
    c.box(22, 3, 23, 5, "g")
    c.box(7, 11, 8, 14, "g")  # écouteur, côté gauche de l'image
    c.box(23, 11, 24, 14, "g")  # écouteur, côté droit
    c.box(9, 15, 9, 17, "g")  # tige du micro
    c.box(10, 17, 11, 17, "g")


def cap(c: Canvas) -> None:
    """Forge : casquette et visière."""
    c.box(9, 3, 22, 7, "K")
    c.box(10, 2, 21, 2, "K")
    c.box(5, 8, 22, 9, "g")  # visière


AGENTS = {
    "finance": {
        "name": "Atlas",
        "hair": "k",
        "accessory": glasses,
        "palette": {
            "k": "#2b2117",
            "s": "#e8b88f",
            "d": "#c08a5f",
            "m": "#9c5c3c",
            "g": "#9aa6bd",
            "c": "#3a4252",
            "v": "#2b3240",
            "a": "#34d399",
            "A": "#7ff0c4",
        },
    },
    "revisions": {
        "name": "Mentor",
        "hair": "k",
        "accessory": bun,
        "palette": {
            "k": "#4a2c17",
            "s": "#f0c9a0",
            "d": "#cf9a6d",
            "m": "#a86244",
            "g": "#9aa6bd",
            "c": "#44405c",
            "v": "#332f47",
            "a": "#fbbf24",
            "A": "#ffe08a",
        },
    },
    "veille": {
        "name": "Vigie",
        "hair": "k",
        "accessory": headset,
        "palette": {
            "k": "#241d33",
            "s": "#d9a07a",
            "d": "#b2744f",
            "m": "#8e4b31",
            "g": "#aab4c8",
            "c": "#37414f",
            "v": "#28303c",
            "a": "#f472b6",
            "A": "#ffa8d6",
        },
    },
    "code": {
        "name": "Forge",
        "hair": "k",
        "accessory": cap,
        "palette": {
            "k": "#241c33",
            "K": "#5a4a85",
            "s": "#c98f68",
            "d": "#a26644",
            "m": "#7e452c",
            "g": "#3b3158",
            "c": "#3b3550",
            "v": "#2c283c",
            "a": "#a78bfa",
            "A": "#d4c6ff",
        },
    },
}


def emit() -> str:
    out: list[str] = []
    out.append(
        '''/* Portraits pixel art des agents, cadrés aux épaules.
 *
 * FICHIER GÉNÉRÉ — ne pas retoucher à la main.
 * Source : scripts/genportraits.py, puis `python3 scripts/genportraits.py`.
 *
 * Grille 32 × 32, un caractère par pixel, résolu via la palette de l'agent.
 * Chaque agent existe en deux états : civil (écran verrouillé) et tenue
 * (console déverrouillée). La tenue est une combinaison bleue commune,
 * barrée d'un baudrier à la couleur de l'agent allant de son épaule gauche
 * à sa hanche droite — le personnage nous faisant face, la bande descend
 * donc de la droite vers la gauche de l'image.
 *
 *   .  transparent   s  peau          c  vêtement civil    u  combinaison
 *   k  cheveux       d  peau (ombre)  v  civil (ombre)     U  combi. claire
 *   K  cheveux clairs m  bouche       a  baudrier          V  combi. ombre
 *   e  pupille       w  blanc de l'œil / insigne
 *   g  équipement (lunettes, casque, visière)   A  liseré du baudrier
 */

export const GRID = 32;

export type Palette = Record<string, string>;

type Portrait = {
  civil: string[];
  uniform: string[];
  palette: Palette;
};

/** Couleurs identiques pour tous : yeux et combinaison de service. */
const SHARED: Palette = {'''
    )
    for key, value in SHARED.items():
        out.append(f'  {key}: "{value}",')
    out.append("};\n")
    out.append("const PORTRAITS: Record<string, Portrait> = {")

    for agent_id, spec in AGENTS.items():
        civil, uniform = build(spec["hair"], spec["accessory"])
        out.append(f"  // {spec['name']}")
        out.append(f"  {agent_id}: {{")
        for label, grid in (("civil", civil), ("uniform", uniform)):
            out.append(f"    {label}: [")
            out.extend(f'      "{r}",' for r in grid)
            out.append("    ],")
        out.append("    palette: {")
        out.append("      ...SHARED,")
        for key, value in spec["palette"].items():
            out.append(f'      {key}: "{value}",')
        out.append("    },")
        out.append("  },")
        out.append("")

    out.append("};\n")
    out.append(
        '''export type PortraitState = "civil" | "uniform";

/** Grille et palette d'un agent dans l'état demandé. */
export function portraitFor(
  agentId: string,
  state: PortraitState,
): { rows: string[]; palette: Palette } | null {
  const entry = PORTRAITS[agentId];
  if (!entry) return null;
  return { rows: state === "civil" ? entry.civil : entry.uniform, palette: entry.palette };
}

export const portraitIds = Object.keys(PORTRAITS);

/** Un agent ajouté au registre sans portrait ne doit pas laisser un cadre vide. */
export const hasPortrait = (agentId: string): boolean => agentId in PORTRAITS;
'''
    )
    return "\n".join(out)


def main() -> None:
    # Vérifie les dimensions avant d'écrire quoi que ce soit.
    used: set[str] = set()
    for agent_id, spec in AGENTS.items():
        for grid in build(spec["hair"], spec["accessory"]):
            assert len(grid) == H, f"{agent_id}: {len(grid)} lignes"
            for i, r in enumerate(grid):
                assert len(r) == W, f"{agent_id} ligne {i}: {len(r)} caracteres"
                used.update(r)

    # Un caractère sans couleur se rendrait en magenta à l'écran.
    known = set(SHARED) | {"."}
    for spec in AGENTS.values():
        known |= set(spec["palette"])
    missing = used - known
    assert not missing, f"caracteres sans couleur : {sorted(missing)}"

    target = pathlib.Path(__file__).resolve().parent.parent / "src" / "portraits.ts"
    target.write_text(emit())
    print(f"OK — 4 agents x 2 etats x {H} lignes de {W} caracteres")
    print(f"ecrit : {target}")


if __name__ == "__main__":
    main()
