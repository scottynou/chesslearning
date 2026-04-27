import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SkillLevelSelector } from "./SkillLevelSelector";

describe("SkillLevelSelector", () => {
  it("shows the three public coach levels", () => {
    render(<SkillLevelSelector value="beginner" onChange={() => undefined} />);
    expect(screen.getByText("Débutant")).toBeTruthy();
    expect(screen.getByText("Intermédiaire")).toBeTruthy();
    expect(screen.getByText("Pro")).toBeTruthy();
  });

  it("emits the selected level", () => {
    const onChange = vi.fn();
    render(<SkillLevelSelector value="beginner" onChange={onChange} />);
    fireEvent.click(screen.getByText("Pro"));
    expect(onChange).toHaveBeenCalledWith("pro");
  });
});
