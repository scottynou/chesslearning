"use client";

const TERMS = [
  ["FEN", "Photo exacte de la position actuelle. Utile pour sauvegarder ou partager une position."],
  ["PGN", "Historique complet des coups d'une partie."],
  ["Elo", "Estimation du niveau du joueur. Ici, il règle le style des coups proposés."],
  ["cp", "Unité utilisée par le moteur. 100 cp correspond environ à un pion d'avantage. En mode débutant, on traduit ça en avantage blanc/noir."],
  ["SAN", "Notation courte utilisée dans les livres et bases de parties, par exemple Nf3."],
  ["UCI", "Notation technique utilisée par les moteurs, par exemple g1f3."],
  ["Roque", "Coup spécial qui met le roi en sécurité et rapproche une tour du centre."],
  ["Prise en passant", "Capture spéciale d'un pion qui vient d'avancer de deux cases."],
  ["Ouverture", "Début de partie : développer les pièces, contrôler le centre et roquer."],
  ["Milieu de partie", "Phase où les plans, attaques et tactiques deviennent plus importants."],
  ["Finale", "Phase avec moins de pièces, où le roi et les pions deviennent essentiels."],
  ["Plan", "Fil conducteur de la partie : ouverture choisie, objectifs actuels et adaptation aux réponses adverses."],
  ["Transposition", "On arrive à une position connue, mais avec un ordre de coups différent."],
  ["Déviation", "L'adversaire ne suit pas la ligne prévue. Le plan peut rester utile, mais doit être adapté."],
  ["Centre", "Les cases d4, e4, d5 et e5. Les contrôler donne souvent plus d'espace."],
  ["Développement", "Sortir les pièces de leur case de départ pour les rendre utiles."],
  ["Colonne ouverte", "Colonne sans pion, souvent idéale pour une tour."],
  ["Case faible", "Case importante difficile à défendre avec un pion."],
  ["Pion isolé", "Pion qui n'a aucun pion ami sur les colonnes voisines."],
  ["Pion doublé", "Deux pions du même camp sur la même colonne."],
  ["Pion passé", "Pion sans pion adverse devant lui ou sur les colonnes voisines."],
  ["Opposition", "Technique de finale où les rois se font face pour gagner l'accès aux cases clés."],
  ["Tablebase", "Base parfaite des finales avec peu de pièces, comme Syzygy."],
  ["Stockfish", "Moteur d'échecs très fort utilisé ici comme garde-fou tactique."],
  ["Maia", "Modèle futur possible pour estimer les coups humains selon le niveau Elo."],
  ["ECO", "Classification des familles d'ouvertures d'échecs."]
] as const;

export function GlossaryPanel() {
  return (
    <section className="panel">
      <h2 className="panel-title">Glossaire</h2>
      <div className="grid gap-2">
        {TERMS.map(([term, definition]) => (
          <details key={term} className="rounded border border-line bg-stone-50 px-3 py-2 text-sm">
            <summary className="cursor-pointer font-semibold text-night">? {term}</summary>
            <p className="mt-1 text-neutral-700">{definition}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
