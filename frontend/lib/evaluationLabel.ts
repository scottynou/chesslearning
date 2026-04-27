export function evaluationLabel(evalCp: number | null, mateIn?: number | null): string {
  if (mateIn !== null && mateIn !== undefined) {
    return `Mat en ${Math.abs(mateIn)}`;
  }
  if (evalCp === null || evalCp === undefined) {
    return "Évaluation inconnue";
  }

  const absolute = Math.abs(evalCp);
  if (absolute < 30) {
    return "Position équilibrée";
  }

  const side = evalCp > 0 ? "blanc" : "noir";
  if (absolute < 80) {
    return `Léger avantage ${side}`;
  }
  if (absolute < 150) {
    return `Avantage clair ${side}`;
  }
  if (absolute < 300) {
    return `Gros avantage ${side}`;
  }
  return `Avantage décisif ${side}`;
}

export function technicalEvaluation(evalCp: number | null, mateIn?: number | null): string {
  if (mateIn !== null && mateIn !== undefined) {
    return `mate ${mateIn}`;
  }
  if (evalCp === null || evalCp === undefined) {
    return "n/a";
  }
  return `${evalCp} cp`;
}
