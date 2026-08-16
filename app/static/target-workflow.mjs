/** Browser-independent target-capture state and geometry. */

const TARGET_SOURCES = new Set(["manual", "full_frame", "roi"]);

function snapshot(state) {
  return { ...state };
}

export function createTargetWorkflow() {
  const state = {
    targetSelected: false,
    selectedTargetSource: "manual",
    selectedTargetPayload: null,
    displayedPaletteSource: "full_frame",
    selectionMode: false,
    roiStart: null,
  };

  return {
    snapshot() {
      return snapshot(state);
    },
    selectTarget(source, payload) {
      if (!TARGET_SOURCES.has(source)) throw new Error(`Unsupported target source: ${source}`);
      state.targetSelected = true;
      state.selectedTargetSource = source;
      state.selectedTargetPayload = payload;
      return snapshot(state);
    },
    resetForNewImage() {
      state.targetSelected = false;
      state.selectedTargetSource = "manual";
      state.selectedTargetPayload = null;
      state.selectionMode = false;
      state.roiStart = null;
      return snapshot(state);
    },
    setDisplayedPaletteSource(source) {
      if (!TARGET_SOURCES.has(source) || source === "manual") {
        throw new Error(`Unsupported palette source: ${source}`);
      }
      state.displayedPaletteSource = source;
      return snapshot(state);
    },
    setSelectionMode(active) {
      state.selectionMode = Boolean(active);
      if (!state.selectionMode) state.roiStart = null;
      return snapshot(state);
    },
    setRoiStart(point) {
      state.roiStart = point ? { x: point.x, y: point.y } : null;
      return snapshot(state);
    },
  };
}

export function imageBoundsFor(imageWidth, imageHeight, container) {
  if (!imageWidth || !imageHeight) return null;
  const scale = Math.min(container.width / imageWidth, container.height / imageHeight);
  const width = imageWidth * scale;
  const height = imageHeight * scale;
  return {
    left: container.left + (container.width - width) / 2,
    top: container.top + (container.height - height) / 2,
    width,
    height,
    container,
  };
}

export function selectionPointFor(event, bounds) {
  return {
    x: Math.min(Math.max(event.clientX, bounds.left), bounds.left + bounds.width),
    y: Math.min(Math.max(event.clientY, bounds.top), bounds.top + bounds.height),
  };
}

export function roiFromSelection(start, end, bounds, imageWidth, imageHeight) {
  const left = Math.min(start.x, end.x);
  const top = Math.min(start.y, end.y);
  const width = Math.abs(end.x - start.x);
  const height = Math.abs(end.y - start.y);
  if (width < 8 || height < 8) return null;
  const scaleX = imageWidth / bounds.width;
  const scaleY = imageHeight / bounds.height;
  return {
    x: Math.round((left - bounds.left) * scaleX),
    y: Math.round((top - bounds.top) * scaleY),
    width: Math.max(1, Math.round(width * scaleX)),
    height: Math.max(1, Math.round(height * scaleY)),
  };
}
