/* Avatars des agents, construits à la volée.
 *
 * Les portraits étaient pré-générés au build tant que la liste d'agents
 * était figée. Depuis qu'on peut en créer, ce n'est plus tenable : un agent
 * inventé par l'utilisateur doit obtenir un visage immédiatement. Le style
 * est donc embarqué et rendu dans le navigateur.
 *
 * Avatars « avataaars » de Pablo Stanley (https://avataaars.com/), libres
 * d'usage personnel et commercial, via DiceBear.
 */

import { Style, Avatar } from "@dicebear/core";
import definition from "@dicebear/styles/avataaars.json";

const style = new Style(definition as never);

/** Combinaison de service : la même pour toute l'équipe. */
const UNIFORM_BLUE = "#2f5d99";

/** Tenue civile — volontairement terne, pour contraster avec la tenue. */
const CIVIL_COLORS = ["#4a5365", "#54506e", "#45505f", "#4b4466", "#3f4a58"];

export type Look = {
  top: string;
  hairColor: string;
  skinColor: string;
  eyes: string;
  eyebrows: string;
  mouth: string;
  /** Variante de lunettes, ou null pour aucun accessoire. */
  accessories: string | null;
};

/* Les listes ci-dessous sont volontairement restreintes : l'inventaire
 * complet d'avataaars contient des expressions (pleurs, nausée, yeux en
 * cœur) qui n'ont pas leur place sur une fiche d'agent. */

export const TOPS = [
  "shortFlat", "shortCurly", "shortRound", "shortWaved", "theCaesar",
  "shaggy", "dreads01", "frizzle", "sides", "bob", "bun", "curly",
  "straight01", "straight02", "longButNotTooLong", "curvy", "fro", "turban",
];

export const EYES = ["default", "happy", "squint", "side", "wink", "closed"];
export const EYEBROWS = ["default", "defaultNatural", "flatNatural", "raisedExcited", "upDown"];
export const MOUTHS = ["default", "smile", "serious", "twinkle", "eating"];
export const ACCESSORIES = [null, "prescription01", "prescription02", "round", "wayfarers"];

export const HAIR_COLORS = [
  "#2c1b18", "#a55728", "#4a312c", "#724133", "#b58143", "#d6b370",
  "#ecdcbf", "#f59797",
];

export const SKIN_COLORS = [
  "#614335", "#ae5d29", "#d08b5b", "#edb98a", "#ffdbb4", "#fd9841",
];

const pick = <T,>(list: readonly T[]): T =>
  list[Math.floor(Math.random() * list.length)];

export function randomLook(): Look {
  return {
    top: pick(TOPS),
    hairColor: pick(HAIR_COLORS),
    skinColor: pick(SKIN_COLORS),
    eyes: pick(EYES),
    eyebrows: pick(EYEBROWS),
    mouth: pick(MOUTHS),
    accessories: pick(ACCESSORIES),
  };
}

const FALLBACK: Look = {
  top: "shortFlat",
  hairColor: "#2c1b18",
  skinColor: "#edb98a",
  eyes: "default",
  eyebrows: "default",
  mouth: "default",
  accessories: null,
};

/** Complète une description partielle — les agents créés avant l'ajout d'un
 *  champ ne doivent pas casser le rendu. */
function normalise(look: Partial<Look> | null | undefined): Look {
  return { ...FALLBACK, ...(look ?? {}) };
}

function build(look: Look, clothesColor: string): string {
  return new Avatar(style, {
    seed: look.top + look.hairColor + look.mouth,
    clothesVariant: { shirtCrewNeck: 1 },
    clothesColor: [clothesColor],
    topVariant: { [look.top]: 1 },
    hairColor: [look.hairColor],
    skinColor: [look.skinColor],
    eyesVariant: { [look.eyes]: 1 },
    eyebrowsVariant: { [look.eyebrows]: 1 },
    mouthVariant: { [look.mouth]: 1 },
    facialHairProbability: 0,
    noseVariant: { default: 1 },
    ...(look.accessories
      ? {
          accessoriesVariant: { [look.accessories]: 1 },
          accessoriesProbability: 100,
          accessoriesColor: ["#929598"],
        }
      : { accessoriesProbability: 0 }),
  }).toString();
}

/**
 * Baudrier diagonal, de l'épaule gauche du personnage vers sa hanche droite.
 * Le personnage nous fait face : la bande descend donc de droite à gauche.
 *
 * La découpe réutilise le tracé réel du vêtement, récupéré dans le SVG
 * rendu. Une forme approchée dessinée à la main débordait de la chemise et
 * laissait traîner la bande sur le fond de la carte.
 */
function addSash(svg: string, accent: string, id: string): string {
  const use = svg.match(/<use transform="([^"]*)" href="#(clothes-[^"]+)"\s*\/>/);
  if (!use) return svg;
  const [, transform, groupId] = use;

  const group = svg.match(new RegExp(`<g id="${groupId}">([\\s\\S]*?)</g>`));
  const path = group?.[1].match(/<path d="([^"]+)"/);
  if (!path) return svg;

  const clip = `sash-${id}`;
  const band = [
    `<defs><clipPath id="${clip}">`,
    `<path transform="${transform}" d="${path[1]}"/>`,
    `</clipPath></defs>`,
    `<g clip-path="url(#${clip})">`,
    `<line x1="214" y1="192" x2="116" y2="290" stroke="${accent}" stroke-width="31"/>`,
    `<line x1="231" y1="192" x2="133" y2="290" stroke="rgba(255,255,255,.2)" stroke-width="6"/>`,
    `</g>`,
  ].join("");

  return svg.replace(/<\/svg>\s*$/, `${band}</svg>`);
}

export type PortraitState = "civil" | "uniform";

/** Construire un avatar coûte quelques millisecondes ; la grille en affiche
 *  deux par agent et re-rend à chaque interaction. */
const cache = new Map<string, string>();

function hash(text: string): number {
  let h = 0;
  for (let i = 0; i < text.length; i += 1) h = (h * 31 + text.charCodeAt(i)) | 0;
  return Math.abs(h);
}

export function renderPortrait(
  look: Partial<Look> | null | undefined,
  state: PortraitState,
  accent: string,
  id: string,
): string {
  const full = normalise(look);
  const key = `${JSON.stringify(full)}|${state}|${accent}|${id}`;
  const hit = cache.get(key);
  if (hit) return hit;

  const civilColor = CIVIL_COLORS[hash(id) % CIVIL_COLORS.length];
  const svg =
    state === "civil"
      ? build(full, civilColor)
      : addSash(build(full, UNIFORM_BLUE), accent, id);

  cache.set(key, svg);
  return svg;
}
