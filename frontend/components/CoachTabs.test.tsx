import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CoachTabs } from "./CoachTabs";

describe("CoachTabs", () => {
  it("makes Plan the first and active priority tab", () => {
    render(<CoachTabs activeTab="plan" onChange={() => undefined} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons[0].textContent).toBe("Plan");
    expect(buttons[0].className).toContain("bg-night");
  });
});
