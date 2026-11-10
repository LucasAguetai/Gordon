import { useCallback, useEffect, useState } from "react";
import { browseFolders, type FolderListing } from "../api";

type Props = {
  value: string | null;
  onChange: (path: string | null) => void;
};

/**
 * Explorateur de dossiers.
 *
 * Un sélecteur de fichiers natif ne donne jamais le vrai chemin disque au
 * navigateur : c'est le serveur qui liste l'arborescence, confinée au
 * dossier personnel.
 */
export default function FolderPicker({ value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [listing, setListing] = useState<FolderListing | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (path?: string) => {
    setError(null);
    try {
      setListing(await browseFolders(path));
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    if (open && !listing) void load(value ?? undefined);
  }, [open, listing, value, load]);

  /** Raccourcit l'affichage : la racine est toujours la même, la répéter
   *  n'apprend rien et fait déborder la ligne. */
  function short(path: string): string {
    const root = listing?.root;
    return root && path.startsWith(root) ? `~${path.slice(root.length)}` : path;
  }

  if (!open) {
    return (
      <div className="picker-closed">
        {value ? (
          <>
            <code className="picker-path">{short(value)}</code>
            <button className="link-btn neutral" onClick={() => setOpen(true)}>
              Changer
            </button>
          </>
        ) : (
          <button className="ghost-btn" onClick={() => setOpen(true)}>
            Choisir un dossier
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="picker">
      <div className="picker-bar">
        <button
          className="ghost-btn"
          disabled={!listing?.parent}
          onClick={() => void load(listing?.parent ?? undefined)}
        >
          ↑
        </button>
        <code className="picker-path">
          {listing ? short(listing.path) : "…"}
        </code>
        <div className="topbar-spacer" />
        <button
          className="ghost-btn"
          onClick={() => {
            if (listing) onChange(listing.path);
            setOpen(false);
          }}
        >
          Utiliser
        </button>
      </div>

      <div className="picker-list">
        {listing?.folders.length === 0 && (
          <p className="picker-empty">Aucun sous-dossier.</p>
        )}
        {listing?.folders.map((folder) => (
          <button
            key={folder.path}
            className="picker-row"
            onClick={() => void load(folder.path)}
          >
            {folder.name}
          </button>
        ))}
      </div>

      {error && <p className="alert">{error}</p>}
    </div>
  );
}
