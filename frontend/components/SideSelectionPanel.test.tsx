import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SideSelectionPanel } from "./SideSelectionPanel";

describe("SideSelectionPanel", () => {
  it("starts with the white or black choice as the main decision", () => {
    render(<SideSelectionPanel onChooseWhite={() => undefined} onChooseBlack={() => undefined} onChooseFreeMode={() => undefined} />);
    expect(screen.getByText("Blancs")).toBeTruthy();
    expect(screen.getByText("Noirs")).toBeTruthy();
    expect(screen.getByText("Mode libre")).toBeTruthy();
  });

  it("calls the black flow when the black choice is clicked", () => {
    const onChooseBlack = vi.fn();
    render(<SideSelectionPanel onChooseWhite={() => undefined} onChooseBlack={onChooseBlack} onChooseFreeMode={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Je joue les noirs" }));
    expect(onChooseBlack).toHaveBeenCalledTimes(1);
  });
});
