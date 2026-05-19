"use client";

import type { StrategyPlan } from "@/lib/types";

type Props = {
  plans: StrategyPlan[];
  currentPlanId: string | null;
  onSelect: (planId: string | null) => void;
  onClose: () => void;
};

export function PlanSwitchModal({ plans, currentPlanId, onSelect, onClose }: Props) {
  return (
    <div className="post-game-review-overlay" role="dialog" aria-modal="true" aria-label="Changer de plan d'ouverture">
      <div className="plan-switch-modal">
        <header className="plan-switch-header">
          <h3>Changer de plan</h3>
          <button type="button" onClick={onClose} aria-label="Fermer" className="saved-games-close">
            ✕
          </button>
        </header>
        <p className="plan-switch-note">
          Garde la position actuelle. Le coach recalcule les conseils avec le nouveau plan.
        </p>
        <ul className="plan-switch-list">
          <li>
            <button
              type="button"
              className={`plan-switch-item ${currentPlanId === null ? "is-active" : ""}`}
              onClick={() => onSelect(null)}
            >
              <span className="plan-switch-name">Aucun plan (jouer par principes)</span>
              <span className="plan-switch-tier">libre</span>
            </button>
          </li>
          {plans.map((plan) => (
            <li key={plan.id}>
              <button
                type="button"
                className={`plan-switch-item ${currentPlanId === plan.id ? "is-active" : ""}`}
                onClick={() => onSelect(plan.id)}
              >
                <span className="plan-switch-name">{plan.nameFr}</span>
                <span className={`plan-switch-tier plan-switch-tier--${plan.tier}`}>{tierLabel(plan.tier)}</span>
                <span className="plan-switch-goal">{plan.beginnerGoal}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function tierLabel(tier: string): string {
  const map: Record<string, string> = {
    recommended: "Recommandé",
    good: "Bon",
    situational: "Situationnel",
    hidden: "Avancé"
  };
  return map[tier] ?? tier;
}
