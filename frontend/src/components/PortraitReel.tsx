import { useId, useMemo } from "react";
import { portraitFor, type PortraitState } from "../portraits";

type Props = {
  agentId: string;
  state: PortraitState;
  size: number;
  /** Désactive la transition — pour les vignettes déjà en tenue. */
  instant?: boolean;
};

/**
 * Préfixe les identifiants internes du SVG.
 *
 * Les portraits sont pré-générés, donc deux rendus du même agent portent
 * exactement les mêmes `id` (masques, tracés de découpe). Affichés en même
 * temps dans la page, les doublons font pointer les masques sur le mauvais
 * élément et le portrait se décompose. On réécrit donc les identifiants à
 * chaque instance.
 */
function namespaceIds(svg: string, prefix: string): string {
  return svg
    .replace(/id="([^"]+)"/g, `id="${prefix}-$1"`)
    .replace(/url\(#([^)]+)\)/g, `url(#${prefix}-$1)`)
    .replace(/((?:xlink:)?href)="#([^"]+)"/g, `$1="#${prefix}-$2"`);
}

function Face({ svg, prefix }: { svg: string; prefix: string }) {
  const html = useMemo(() => namespaceIds(svg, prefix), [svg, prefix]);
  // Contenu produit au build par scripts/genportraits.mjs : aucune donnée
  // utilisateur n'y transite.
  return <div className="reel-cell" dangerouslySetInnerHTML={{ __html: html }} />;
}

/**
 * Portrait à deux états montés l'un au-dessus de l'autre. Le passage de
 * « civil » à « tenue » fait défiler la bobine vers le haut.
 */
export default function PortraitReel({ agentId, state, size, instant }: Props) {
  const rawId = useId();
  // useId produit des deux-points, qui cassent les références url(#…).
  const prefix = rawId.replace(/[^a-zA-Z0-9]/g, "");

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
        <Face svg={civil} prefix={`${prefix}c`} />
        <Face svg={uniform} prefix={`${prefix}u`} />
      </div>
    </div>
  );
}
