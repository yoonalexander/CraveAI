import { render } from "@testing-library/react";
import { expect, it } from "vitest";
import { CUISINE_OPTIONS } from "../utils/suggestionPool";
import { CuisineIcon } from "./CuisineIcon";

it("covers the cuisine catalog with decorative dish art and safely falls back for unknown labels", () => {
  const { container } = render(<>{CUISINE_OPTIONS.map((cuisine) => <CuisineIcon key={cuisine} cuisine={cuisine} />)}</>);
  const icons = [...container.querySelectorAll("svg")];
  expect(icons).toHaveLength(CUISINE_OPTIONS.length);
  for (const icon of icons) {
    expect(icon).not.toHaveAttribute("data-food-icon", "plate");
    expect(icon).toHaveAttribute("aria-hidden", "true");
    expect(icon).toHaveAttribute("focusable", "false");
    expect(icon.children.length).toBeGreaterThan(0);
  }
  const { container: unknown } = render(<><CuisineIcon cuisine="Ethiopian" /><CuisineIcon cuisine="constructor" /><CuisineIcon /><CuisineIcon cuisine="  JAPANESE  " /></>);
  expect([...unknown.querySelectorAll("svg")].map((icon) => icon.getAttribute("data-food-icon"))).toEqual(["plate", "plate", "plate", "sushi"]);
});
