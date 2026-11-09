/* Génère les portraits des agents et réécrit src/portraits.ts.
 *
 * Les avatars viennent d'avataaars (Pablo Stanley), via DiceBear. Chaque
 * agent est composé à la main : laisser la graine choisir au hasard donne
 * quatre inconnus aux expressions incohérentes, pas une équipe.
 *
 * Les SVG sont pré-générés ici plutôt que construits dans le navigateur :
 * la seule définition d'avataaars pèse 125 Ko, contre ~38 Ko pour les huit
 * portraits finis. DiceBear reste donc une devDependency.
 *
 * Lancement :  cd frontend && node scripts/genportraits.mjs
 */

import { Style, Avatar } from "@dicebear/core";
import definition from "@dicebear/styles/avataaars.json" with { type: "json" };
import fs from "node:fs";
import path from "node:path";

const OUT = path.join(
  path.dirname(new URL(import.meta.url).pathname),
  "..",
  "src",
  "portraits.ts",
);

/** Combinaison de service : la même pour toute l'équipe. */
const UNIFORM_BLUE = "#2f5d99";

/** Traits communs — ce qui fait que les quatre forment une équipe. */
const COMMON = {
  clothesVariant: { shirtCrewNeck: 1 },
  facialHairProbability: 0,
  noseVariant: { default: 1 },
};

const AGENTS = [
  {
    id: "finance",
    name: "Atlas",
    accent: "#34d399",
    civilClothes: "#4a5365",
    look: {
      topVariant: { shortFlat: 1 },
      hairColor: ["#2c1b18"],
      accessoriesVariant: { prescription02: 1 },
      accessoriesProbability: 100,
      accessoriesColor: ["#929598"],
      eyesVariant: { default: 1 },
      eyebrowsVariant: { default: 1 },
      mouthVariant: { serious: 1 },
      skinColor: ["#edb98a"],
    },
  },
  {
    id: "revisions",
    name: "Mentor",
    accent: "#fbbf24",
    civilClothes: "#54506e",
    look: {
      topVariant: { bob: 1 },
      hairColor: ["#a55728"],
      accessoriesProbability: 0,
      eyesVariant: { happy: 1 },
      eyebrowsVariant: { defaultNatural: 1 },
      mouthVariant: { smile: 1 },
      skinColor: ["#ffdbb4"],
    },
  },
  {
    id: "veille",
    name: "Vigie",
    accent: "#f472b6",
    civilClothes: "#45505f",
    look: {
      topVariant: { straight02: 1 },
      hairColor: ["#4a312c"],
      accessoriesProbability: 0,
      eyesVariant: { default: 1 },
      eyebrowsVariant: { default: 1 },
      mouthVariant: { default: 1 },
      skinColor: ["#d08b5b"],
    },
  },
  {
    id: "code",
    name: "Forge",
    accent: "#a78bfa",
    civilClothes: "#4b4466",
    look: {
      topVariant: { shortCurly: 1 },
      hairColor: ["#2c1b18"],
      accessoriesProbability: 0,
      eyesVariant: { default: 1 },
      eyebrowsVariant: { default: 1 },
      mouthVariant: { twinkle: 1 },
      skinColor: ["#ae5d29"],
    },
  },
];

const style = new Style(definition);

function render(agent, clothesColor) {
  return new Avatar(style, {
    seed: agent.name,
    ...COMMON,
    ...agent.look,
    clothesColor: [clothesColor],
  }).toString();
}

/**
 * Récupère la silhouette exacte de la chemise dans le SVG rendu.
 *
 * Le vêtement est défini dans `<defs>` en coordonnées locales, puis posé
 * sur le canevas par un `<use transform=…>`. On réutilise les deux pour
 * découper le baudrier : une forme approximative dessinée à la main
 * débordait de la chemise et laissait la bande traîner sur le fond de la
 * carte — ce qui se voyait comme une zone grise sous l'épaule.
 */
function shirtSilhouette(svg) {
  const use = svg.match(/<use transform="([^"]*)" href="#(clothes-[^"]+)"\s*\/>/);
  if (!use) throw new Error("placement du vêtement introuvable");
  const [, transform, groupId] = use;

  const group = svg.match(new RegExp(`<g id="${groupId}">([\\s\\S]*?)</g>`));
  if (!group) throw new Error(`groupe ${groupId} introuvable`);

  // Le premier tracé du groupe est le contour du vêtement ; les suivants
  // sont le col et les plis.
  const path = group[1].match(/<path d="([^"]+)"/);
  if (!path) throw new Error("contour du vêtement introuvable");

  return { d: path[1], transform };
}

/**
 * Baudrier diagonal, de l'épaule gauche du personnage vers sa hanche
 * droite. Le personnage nous fait face : son épaule gauche est donc à
 * droite de l'image, et la bande descend de droite à gauche.
 *
 * La pente est volontairement marquée pour que l'extrémité basse arrive à
 * la taille. Une diagonale plus douce traverse le buste presque à
 * l'horizontale et ne lit plus comme un baudrier.
 */
const SASH = {
  x1: 214,
  y1: 192,
  x2: 116,
  y2: 290,
  width: 31,
  /** Décalage du liseré, le long de la normale à la bande. */
  gloss: 17,
};

function sash(agent, shirt) {
  const id = `sash-${agent.id}`;
  const { x1, y1, x2, y2, width, gloss } = SASH;
  return [
    `<defs><clipPath id="${id}">`,
    `<path transform="${shirt.transform}" d="${shirt.d}"/>`,
    `</clipPath></defs>`,
    `<g clip-path="url(#${id})">`,
    `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"`,
    ` stroke="${agent.accent}" stroke-width="${width}"/>`,
    `<line x1="${x1 + gloss}" y1="${y1}" x2="${x2 + gloss}" y2="${y2}"`,
    ` stroke="rgba(255,255,255,.2)" stroke-width="6"/>`,
    `</g>`,
  ].join("");
}

/** Insère le baudrier juste avant la fermeture du SVG. */
function withSash(svg, agent) {
  const shirt = shirtSilhouette(svg);
  return svg.replace(/<\/svg>\s*$/, `${sash(agent, shirt)}</svg>`);
}

const entries = AGENTS.map((agent) => {
  const civil = render(agent, agent.civilClothes);
  const uniform = withSash(render(agent, UNIFORM_BLUE), agent);
  return { agent, civil, uniform };
});

const body = entries
  .map(
    ({ agent, civil, uniform }) => `  // ${agent.name}
  ${agent.id}: {
    civil: ${JSON.stringify(civil)},
    uniform: ${JSON.stringify(uniform)},
  },`,
  )
  .join("\n");

fs.writeFileSync(
  OUT,
  `/* Portraits des agents.
 *
 * FICHIER GÉNÉRÉ — ne pas retoucher à la main.
 * Source : scripts/genportraits.mjs, puis \`node scripts/genportraits.mjs\`.
 *
 * Avatars « avataaars » de Pablo Stanley (https://avataaars.com/), libres
 * d'usage personnel et commercial, générés via DiceBear puis composés agent
 * par agent. Deux états : civil (console verrouillée) et tenue de service
 * (déverrouillée) — combinaison bleue commune barrée d'un baudrier à la
 * couleur de l'agent, de son épaule gauche vers sa hanche droite.
 */

type Portrait = { civil: string; uniform: string };

const PORTRAITS: Record<string, Portrait> = {
${body}
};

export type PortraitState = "civil" | "uniform";

/** SVG brut du portrait, dans l'état demandé. */
export function portraitFor(
  agentId: string,
  state: PortraitState,
): string | null {
  return PORTRAITS[agentId]?.[state] ?? null;
}

export const portraitIds = Object.keys(PORTRAITS);

/** Un agent ajouté au registre sans portrait ne doit pas laisser un cadre vide. */
export const hasPortrait = (agentId: string): boolean => agentId in PORTRAITS;
`,
);

console.log(`OK — ${entries.length} agents x 2 états`);
console.log(`écrit : ${OUT}`);
