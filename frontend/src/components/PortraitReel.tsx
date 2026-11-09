import { useId, useMemo } from "react";
import { renderPortrait, type Look, type PortraitState } from "../avatar";

type Props = {
  look: Partial<Look> | null | undefined;
  accent: string;
  /** Rend les identifiants internes du SVG uniques et stables. */
  id: string;
  state: PortraitState;
  size: number;
  /** Désactive la transition — pour les vignettes déjà en tenue. */
  instant?: boolean;
};

/**
 * Préfixe les identifiants internes du SVG.
 *
 * Deux portraits construits à partir de la même description portent les
 * mêmes `id` (masques, tracés de découpe). Affichés en même temps dans la
 * page, les doublons font pointer les masques sur le mauvais élément et le
 * portrait se décompose.
 */
function namespaceIds(svg: string, prefix: string): string {
  return svg
    .replace(/id="([^"]+)"/g, `id="${prefix}-$1"`)
    .replace(/url\(#([^)]+)\)/g, `url(#${prefix}-$1)`)
    .replace(/((?:xlink:)?href)="#([^"]+)"/g, `$1="#${prefix}-$2"`);
}

function Face({
  look,
  accent,
  id,
  state,
  prefix,
}: Omit<Props, "size" | "instant"> & { prefix: string }) {
  const html = useMemo(
    () => namespaceIds(renderPortrait(look, state, accent, id), prefix),
    [look, accent, id, state, prefix],
  );
  // Contenu produit localement par avatar.ts : aucune donnée utilisateur
  // n'y transite, le texte saisi dans le formulaire ne touche pas le SVG.
  return <div className="reel-cell" dangerouslySetInnerHTML={{ __html: html }} />;
}

/**
 * Portrait à deux états montés l'un au-dessus de l'autre. Le passage de
 * « civil » à « tenue » fait défiler la bobine vers le haut.
 */
export default function PortraitReel({
  look,
  accent,
  id,
  state,
  size,
  instant,
}: Props) {
  const rawId = useId();
  // useId produit des deux-points, qui cassent les références url(#…).
  const prefix = rawId.replace(/[^a-zA-Z0-9]/g, "");

  return (
    <div
      className={`reel${instant ? " reel-instant" : ""}`}
      style={{ width: size, height: size }}
    >
      <div
        className="reel-track"
        style={{ transform: state === "uniform" ? `translateY(-${size}px)` : "none" }}
      >
        <Face
          look={look}
          accent={accent}
          id={id}
          state="civil"
          prefix={`${prefix}c`}
        />
        <Face
          look={look}
          accent={accent}
          id={id}
          state="uniform"
          prefix={`${prefix}u`}
        />
      </div>
    </div>
  );
}
