import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// `globals` is disabled in vitest.config, so Testing Library's automatic
// afterEach cleanup never registers itself. Wire it up explicitly so each test
// starts from an empty DOM instead of leaking mounted components into the next.
afterEach(cleanup);
