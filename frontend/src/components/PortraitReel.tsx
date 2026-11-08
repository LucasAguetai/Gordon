import { useMemo } from "react";
import { GRID, portraitFor, type Palette, type PortraitState } from "../portraits";

type Props = {
  agentId: string;
  state: PortraitState;
  size: number;
  /** Désactive la transition — utile pour les vignettes déjà en tenue. */
  instant?: boolean;
};

/** Un pixel ou une suite horizontale de pixels de même couleur. */
type Run = { x: number; y: number; w: number; fill: string };

/**
 * Fusionne les pixels voisins de même couleur en segments.
 * Une grille 16×16 rendue pixel par pixel produit jusqu'à 256 nœuds SVG par
 * portrait, et il y en a deux par bobine : le regroupement par lignes divise
 * ce nombre par cinq environ, ce qui compte quand huit portraits s'animent
 * en même temps.
 */
function toRuns(rows: string[], palette: Palette): Run[] {
  const runs: Run[] = [];

  rows.forEach((row, y) => {
    let x = 0;
    while (x < row.length) {
      const ch = row[x];
      if (ch === ".") {
        x += 1;
        continue;
      }
      let w = 1;
      while (x + w < row.length && row[x + w] === ch) w += 1;

      const fill = palette[ch];
      // Un caractère absent de la palette est une coquille dans la grille :
      // on le rend en magenta plutôt que de le masquer silencieusement.
      runs.push({ x, y, w, fill: fill ?? "#ff00ff" });
      x += w;
    }
  });

  return runs;
}

function PixelFace({ rows, palette }: { rows: string[]; palette: Palette }) {
  const runs = useMemo(() => toRuns(rows, palette), [rows, palette]);

  return (
    <svg
      viewBox={`0 0 ${GRID} ${GRID}`}
      shapeRendering="crispEdges"
      aria-hidden="true"
      focusable="false"
    >
      {runs.map((run) => (
        <rect
          key={`${run.x}-${run.y}`}
          x={run.x}
          y={run.y}
          width={run.w}
          height={1}
          fill={run.fill}
        />
      ))}
    </svg>
  );
}

/**
 * Portrait à deux états montés l'un au-dessus de l'autre. Le passage de
 * « civil » à « tenue » fait défiler la bobine vers le haut, comme une
 * planche de portraits qui tourne.
 */
export default function PortraitReel({ agentId, state, size, instant }: Props) {
  const civil = portraitFor(agentId, "civil");
  const uniform = portraitFor(agentId, "uniform");
  if (!civil || !uniform) return null;

  return (
    <div
      className={`reel${instant ? " reel-instant" : ""}`}
      style={{ width: size, height: size }}
    >
      <div
        className="reel-track"
        style={{ transform: state === "uniform" ? `translateY(-${size}px)` : "none" }}
      >
        <div className="reel-cell" style={{ width: size, height: size }}>
          <PixelFace rows={civil.rows} palette={civil.palette} />
        </div>
        <div className="reel-cell" style={{ width: size, height: size }}>
          <PixelFace rows={uniform.rows} palette={uniform.palette} />
        </div>
      </div>
    </div>
  );
}
