import test from "node:test";
import assert from "node:assert/strict";

import {
  createTargetWorkflow,
  imageBoundsFor,
  roiFromSelection,
  selectionPointFor,
} from "../app/static/target-workflow.mjs";

test("target workflow keeps target provenance and resets on a new image", () => {
  const workflow = createTargetWorkflow();

  workflow.selectTarget("roi", { hex: "#D0362B" });
  assert.deepEqual(workflow.snapshot(), {
    targetSelected: true,
    selectedTargetSource: "roi",
    selectedTargetPayload: { hex: "#D0362B" },
    displayedPaletteSource: "full_frame",
    selectionMode: false,
    roiStart: null,
  });

  workflow.resetForNewImage();
  assert.equal(workflow.snapshot().targetSelected, false);
  assert.equal(workflow.snapshot().selectedTargetSource, "manual");
});

test("target workflow converts bounded pointer coordinates into an image ROI", () => {
  const bounds = imageBoundsFor(1000, 500, { left: 10, top: 20, width: 500, height: 300 });
  assert.deepEqual(bounds, {
    left: 10,
    top: 45,
    width: 500,
    height: 250,
    container: { left: 10, top: 20, width: 500, height: 300 },
  });

  assert.deepEqual(selectionPointFor({ clientX: -10, clientY: 400 }, bounds), { x: 10, y: 295 });
  assert.deepEqual(
    roiFromSelection({ x: 110, y: 145 }, { x: 310, y: 245 }, bounds, 1000, 500),
    { x: 200, y: 200, width: 400, height: 200 },
  );
  assert.equal(roiFromSelection({ x: 110, y: 145 }, { x: 115, y: 245 }, bounds, 1000, 500), null);
});
