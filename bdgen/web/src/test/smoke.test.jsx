import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

describe("vitest setup", () => {
  it("renders a React tree into jsdom", () => {
    render(<div data-testid="hello">hello</div>);
    expect(screen.getByTestId("hello")).toHaveTextContent("hello");
  });
});
