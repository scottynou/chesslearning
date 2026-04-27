export const ELO_STEPS = [
  600, 800, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2400, 2600, 2800, 3000, 3200
] as const;

export function nearestEloStep(value: number): number {
  return ELO_STEPS.reduce((nearest, step) => {
    return Math.abs(step - value) < Math.abs(nearest - value) ? step : nearest;
  }, ELO_STEPS[0]);
}
