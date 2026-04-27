import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CandidateMoveList } from "./CandidateMoveList";
import type { CandidateMove } from "@/lib/types";

const candidate: CandidateMove = {
  rank: 1,
  moveUci: "g8f6",
  moveSan: "Nf6",
  stockfishRank: 2,
  evalCp: -31,
  mateIn: null,
  pv: ["g8f6", "e2e3", "c7c5"],
  coachScore: 88,
  engineScore: 82,
  humanLikelihood: 72,
  simplicityScore: 78,
  riskPenalty: 12,
  difficulty: "medium",
  risk: "medium",
  summary: "Sortir le cavalier et contrôler le centre."
};

describe("CandidateMoveList", () => {
  it("shows beginner labels and hides cp from the main card", () => {
    const { container } = render(
      <CandidateMoveList
        fen="rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1"
        candidates={[candidate]}
        selectedMove={null}
        loading={false}
        onSelect={() => undefined}
      />
    );

    expect(screen.getByText("♞ Cavalier g8 → f6")).toBeTruthy();
    expect(screen.getByText("Évaluation : Léger avantage noir")).toBeTruthy();
    expect(container.querySelector("button")?.textContent).not.toContain("-31 cp");
  });

  it("calls onSelect when a candidate is clicked", () => {
    const onSelect = vi.fn();
    render(
      <CandidateMoveList
        fen="rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1"
        candidates={[candidate]}
        selectedMove={null}
        loading={false}
        onSelect={onSelect}
      />
    );

    fireEvent.click(screen.getByText("Comprendre ce coup"));
    expect(onSelect).toHaveBeenCalledWith(candidate);
  });
});
