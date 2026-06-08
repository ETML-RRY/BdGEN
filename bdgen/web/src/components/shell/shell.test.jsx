import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppContext } from "../../context/AppContext.jsx";
import Ribbon from "./Ribbon.jsx";
import Sidebar from "./Sidebar.jsx";

function wrap(value, ui) {
  return render(<AppContext.Provider value={value}>{ui}</AppContext.Provider>);
}

function wrapRouter(value, ui, route = "/projects/p/compose") {
  return render(
    <AppContext.Provider value={value}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </AppContext.Provider>,
  );
}

const META = { name: "p", displayName: "Projet P" };

describe("Ribbon", () => {
  it("renders command groups from the model and fires onClick", () => {
    const onClick = vi.fn();
    const ribbon = { groups: [{ id: "g", label: "Génération", commands: [{ id: "c", label: "Générer", onClick }] }] };
    wrapRouter({ ribbon, projectMeta: META }, <Ribbon />);
    expect(screen.getByText("Générer")).toBeInTheDocument();
    fireEvent.click(screen.getByTitle("Générer"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("renders the phase tabs as the tab strip and marks the active phase", () => {
    wrapRouter({ ribbon: null, projectMeta: META }, <Ribbon />);
    // Phases come from STEPS — the route is on "compose" → "Pages" is active.
    // i18n is initialised in test/setup.js with lng="en".
    expect(screen.getByRole("tab", { name: "Preparation" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Pages" })).toHaveClass("active");
  });

  it("renders nothing outside a project", () => {
    const { container } = wrapRouter({ ribbon: null, projectMeta: null }, <Ribbon />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("Sidebar", () => {
  it("renders sections/items and reports selection", () => {
    const onSelect = vi.fn();
    const sidebar = {
      sections: [{ id: "s", label: "Personnages", items: [{ id: "a", label: "Alice" }, { id: "b", label: "Bob" }] }],
      activeItem: "a",
      onSelect,
    };
    wrap({ sidebar }, <Sidebar />);
    expect(screen.getByText("Personnages")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Bob"));
    expect(onSelect).toHaveBeenCalledWith("b");
  });

  it("renders nothing without a model", () => {
    const { container } = wrap({ sidebar: null }, <Sidebar />);
    expect(container).toBeEmptyDOMElement();
  });
});
