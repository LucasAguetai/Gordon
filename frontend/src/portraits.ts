/* Portraits pixel art des agents, cadrés aux épaules.
 *
 * Chaque portrait est une grille de 16 × 16 décrite en texte : un caractère
 * par pixel, résolu via la palette de l'agent. Le format est volontairement
 * lisible pour pouvoir retoucher un visage directement dans le fichier.
 *
 * La tête (12 lignes) est commune aux deux états : c'est la même personne,
 * seule la tenue change. Le buste (4 lignes) porte la différence entre civil
 * et tenue de service.
 *
 *   .  transparent      s  peau            c  vêtement civil
 *   k  cheveux          d  peau (ombre)    a  tenue (couleur d'accent)
 *   K  cheveux clairs   m  bouche          w  insigne
 *   e  œil              g  équipement (lunettes, casque, visière)
 *
 * Les grilles sont produites par scratchpad/genportraits.py, qui décrit
 * chaque ligne en paires (caractère, répétitions) : les largeurs sont donc
 * justes par construction. Une retouche ponctuelle peut se faire ici
 * directement, à condition de garder 16 caractères par ligne.
 */

export const GRID = 16;

export type Palette = Record<string, string>;

type Portrait = {
  head: string[];
  palette: Palette;
};

const TORSO_CIVIL = [
  "....cccccccc....",
  "..cccccccccccc..",
  ".cccccccccccccc.",
  ".cccccccccccccc.",
];

const TORSO_UNIFORM = [
  "....caaaaaac....",
  "..ccaaaaaaaacc..",
  ".cccaaaaaaaaccc.",
  ".ccaaaawwaaaacc.",
];

/** Peau et œil sont communs : la distinction se fait sur cheveux et tenue. */
const SKIN = { e: "#17120d", w: "#f4f7ff" };

const PORTRAITS: Record<string, Portrait> = {
  // Atlas — lunettes, coupe nette.
  finance: {
    head: [
      "................",
      "....kkkkkkkk....",
      "...kkkkkkkkkk...",
      "...kksssssskk...",
      "...kssssssssk...",
      "...kgegssgegk...",
      "...kssssssssk...",
      "...ksssddsssk...",
      "...kssssssssk...",
      "...kssmmmmssk...",
      ".....ssssss.....",
      "......dddd......",
    ],
    palette: {
      ...SKIN,
      k: "#2b2117",
      s: "#e8b88f",
      d: "#c89468",
      m: "#9c6442",
      g: "#8a93a6",
      c: "#3a4252",
      a: "#34d399",
    },
  },

  // Mentor — chignon haut, mèches longues.
  revisions: {
    head: [
      "......kkkk......",
      "....kkkkkkkk....",
      "...kkkkkkkkkk...",
      "..kkksssssskkk..",
      "..kksssssssskk..",
      "..kkssessesskk..",
      "..kksssssssskk..",
      "..kksssddssskk..",
      "..kksssssssskk..",
      "..kkssmmmmsskk..",
      ".....ssssss.....",
      "......dddd......",
    ],
    palette: {
      ...SKIN,
      k: "#4a2c17",
      s: "#f0c9a0",
      d: "#d0a076",
      m: "#a86f4c",
      g: "#8a93a6",
      c: "#44405c",
      a: "#fbbf24",
    },
  },

  // Vigie — casque d'écoute.
  veille: {
    head: [
      "................",
      "....kkkkkkkk....",
      "..gggggggggggg..",
      "..gkksssssskkg..",
      "..gksssssssskg..",
      "..gkssessesskg..",
      "..gksssssssskg..",
      "...ksssddsssk...",
      "...kssssssssk...",
      "...kssmmmmssk...",
      ".....ssssss.....",
      "......dddd......",
    ],
    palette: {
      ...SKIN,
      k: "#1f1b2e",
      s: "#d9a07a",
      d: "#b87f5c",
      m: "#8e5438",
      g: "#a7b0c4",
      c: "#37414f",
      a: "#f472b6",
    },
  },

  // Forge — casquette à visière.
  code: {
    head: [
      "................",
      "...KKKKKKKKKK...",
      "..KKKKKKKKKKKK..",
      "..gggggggggggg..",
      "...kssssssssk...",
      "...kssessessk...",
      "...kssssssssk...",
      "...ksssddsssk...",
      "...kssssssssk...",
      "...kssmmmmssk...",
      ".....ssssss.....",
      "......dddd......",
    ],
    palette: {
      ...SKIN,
      k: "#241c33",
      K: "#4c3f6b",
      s: "#c98f68",
      d: "#a97250",
      m: "#7e4a30",
      g: "#2e2644",
      c: "#3b3550",
      a: "#a78bfa",
    },
  },
};

export type PortraitState = "civil" | "uniform";

/** Portrait complet (tête + buste) pour un agent et un état donnés. */
export function portraitFor(
  agentId: string,
  state: PortraitState,
): { rows: string[]; palette: Palette } | null {
  const entry = PORTRAITS[agentId];
  if (!entry) return null;
  return {
    rows: [...entry.head, ...(state === "civil" ? TORSO_CIVIL : TORSO_UNIFORM)],
    palette: entry.palette,
  };
}

export const portraitIds = Object.keys(PORTRAITS);

/** Un agent ajouté au registre sans portrait ne doit pas laisser un cadre vide. */
export const hasPortrait = (agentId: string): boolean => agentId in PORTRAITS;
