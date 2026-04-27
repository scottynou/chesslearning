"use client";

const TERMS = [
  ["FEN", "Photo exacte de la position actuelle. Utile pour sauvegarder ou partager une position."],
  ["PGN", "Historique complet des coups d'une partie."],
  ["Elo", "Estimation du niveau du joueur. Ici, il regle surtout le style des coups proposes."],
  ["cp", "Unite du moteur. 100 cp correspond environ a un pion d'avantage."],
  ["SAN", "Notation courte utilisee dans les livres et bases de parties, par exemple Nf3."],
  ["UCI", "Notation technique utilisee par les moteurs, par exemple g1f3."],
  ["Roque", "Coup special qui met le roi en securite et rapproche une tour du centre."],
  ["Prise en passant", "Capture speciale d'un pion qui vient d'avancer de deux cases."],
  ["Ouverture", "Debut de partie : developper les pieces, controler le centre et roquer."],
  ["Milieu de partie", "Phase ou les plans, attaques et tactiques deviennent plus importants."],
  ["Finale", "Phase avec moins de pieces, ou le roi et les pions deviennent essentiels."],
  ["Plan", "Fil conducteur de la partie : ouverture choisie, objectifs actuels et adaptations."],
  ["Transposition", "On arrive a une position connue, mais avec un ordre de coups different."],
  ["Deviation", "L'adversaire ne suit pas la ligne prevue. Le plan reste utile, mais il faut l'adapter."],
  ["Centre", "Les cases d4, e4, d5 et e5. Les controler donne souvent plus d'espace."],
  ["Developpement", "Sortir les pieces de leur case de depart pour les rendre utiles."],
  ["Colonne ouverte", "Colonne sans pion, souvent ideale pour une tour."],
  ["Case faible", "Case importante difficile a defendre avec un pion."],
  ["Pion isole", "Pion qui n'a aucun pion ami sur les colonnes voisines."],
  ["Pion double", "Deux pions du meme camp sur la meme colonne."],
  ["Pion passe", "Pion sans pion adverse devant lui ou sur les colonnes voisines."],
  ["Opposition", "Technique de finale ou les rois se font face pour gagner l'acces aux cases cles."],
  ["Tablebase", "Base parfaite des finales avec peu de pieces, comme Syzygy."],
  ["Stockfish", "Moteur d'echecs tres fort utilise ici comme garde-fou tactique."],
  ["Maia", "Modele futur possible pour estimer les coups humains selon le niveau Elo."],
  ["ECO", "Classification des familles d'ouvertures d'echecs."],
  ["Gambit", "Sacrifice volontaire, souvent un pion, pour obtenir du temps, du centre ou de l'activite."],
  ["Fianchetto", "Developper un fou sur b2, g2, b7 ou g7 pour viser une grande diagonale."],
  ["Clouage", "Une piece ne peut pas bouger sans exposer une piece plus importante derriere elle."],
  ["Fourchette", "Une piece attaque deux cibles en meme temps."],
  ["Rupture", "Coup de pion qui ouvre ou conteste une structure bloquee."],
  ["Structure de pions", "Forme des pions. Elle indique souvent ou jouer et quelles cases sont faibles."]
] as const;

export function GlossaryPanel({ compact = false }: { compact?: boolean }) {
  return (
    <section className={compact ? "glossary-compact" : "panel"}>
      {compact ? null : <h2 className="panel-title">Glossaire</h2>}
      <div className="grid gap-2">
        {TERMS.map(([term, definition]) => (
          <details key={term} className={compact ? "glossary-compact-item" : "rounded border border-line bg-stone-50 px-3 py-2 text-sm"}>
            <summary className="cursor-pointer font-semibold text-night">? {term}</summary>
            <p className="mt-1 text-neutral-700">{definition}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
