const $ = (selector) => document.querySelector(selector);
const materials = $("#materials");
const translations = {
  en: {
    pageTitle: "Chromix — Color intelligence prototype",
    pageDescription: "Turn a product photo into an inventory-aware digital color recipe.",
    status: "formulation engine online",
    languageLabel: "LANGUAGE",
    eyebrow: "COLOR INTELLIGENCE / MANUFACTURING",
    heroTitleBefore: "From product photo<br>to ",
    heroTitleAccent: "mixing recipe.",
    heroDescription: "Choose the color your customer wants. Estimate a mix from materials you already have. Scale every ingredient to the exact batch.",
    workflow: "Workflow",
    capture: "Capture",
    analyze: "Analyze",
    formulate: "Formulate",
    colorCapture: "COLOR CAPTURE",
    colorQuestion: "What color are we making?",
    uploadImage: "Upload a product image",
    dropImage: "Drop a product image here",
    browseImage: "or click to browse · PNG, JPG, WEBP",
    uploadedPreview: "Uploaded product preview",
    extractedPalette: "EXTRACTED PALETTE",
    awaitingImage: "Awaiting image",
    paletteSource: "Palette source",
    fullFrame: "FULL FRAME",
    selectRegion: "SELECT REGION",
    selectionHelp: "Choose a swatch, enter a hex value, or select a region before formulating.",
    targetColor: "Target color",
    copyColor: "Copy color",
    copy: "COPY",
    copied: "COPIED",
    manualTarget: "Manual target",
    noImageTarget: "No image target selected",
    selectedAnalyzedRegion: "Selected from the analyzed region",
    selectedFullFrame: "Selected from the full-frame palette",
    rgb: "RGB",
    rgbaHex: "RGBA HEX",
    lab: "LAB",
    calculatedOnMix: "Calculated on mix",
    formulationEstimate: "FORMULATION ESTIMATE",
    buildPrototype: "Build the prototype mix.",
    productionBatch: "Production batch",
    totalRequiredMaterial: "Total required material",
    material: "MATERIAL",
    color: "COLOR",
    available: "AVAILABLE",
    strength: "STRENGTH",
    costPerKg: "COST / KG",
    materialName: "Material name",
    materialColor: "Material color",
    availableKg: "Available kilograms",
    relativeTintStrength: "Relative tint strength",
    costPerKgLabel: "Cost per kilogram",
    removeMaterial: "Remove material",
    addMaterial: "Add material",
    newPigment: "New pigment",
    materialNaturalResin: "Natural resin",
    materialCarbonBlack: "Carbon black",
    materialSignalRed: "Signal red",
    materialWarmYellow: "Warm yellow",
    materialUltramarine: "Ultramarine",
    calculateFormula: "CALCULATE FORMULA",
    optimizing: "OPTIMIZING…",
    ready: "READY",
    target: "TARGET",
    predicted: "PREDICTED",
    colorDifference: "COLOR DIFFERENCE",
    runFormulation: "Run the formulation engine to compare the digital target and predicted mix.",
    emptyRecipe: "Your ingredient recipe will appear here.",
    totalBatch: "TOTAL BATCH",
    modelNote: "Digital estimate. Production recipes require calibration using measured material samples.",
    lessTrial: "Less trial & error",
    lessTrialText: "Optimize before the first physical batch.",
    inventoryAware: "Inventory aware",
    inventoryAwareText: "Never recommend material you don't have.",
    scaleInstantly: "Scale instantly",
    scaleInstantlyText: "From a 1 kg sample to large-batch planning.",
    footerTagline: "COLOR SCIENCE × MATERIAL INTELLIGENCE",
    selectedRegionMeta: "selected region",
    fullFrameMeta: "full frame",
    pixels: "px",
    regionHelp: "Region analyzed. Choose a swatch or use Full Frame to compare against the complete image.",
    fullFrameHelp: "Full-frame palette shown. Choose a swatch or select a region; the largest cluster is not auto-selected.",
    uploadBeforeRegion: "Upload an image before selecting a region.",
    dragRegion: "Drag across the product area in the image to analyze only that region.",
    cancelRegion: "Region selection cancelled. Choose a swatch or use the full-frame palette.",
    scoreClose: "Visually very close in this digital model.",
    scoreNoMatch: "The current inventory cannot reproduce the target exactly in this digital model.",
    estimated: "est.",
    estimatedCost: "est.",
    estimatedTotal: "EST.",
    qualityExcellent: "EXCELLENT",
    qualityGood: "GOOD",
    qualityApproximate: "APPROXIMATE",
    qualityNeedsCalibration: "NEEDS CALIBRATION",
    couldNotAnalyze: "Could not analyze the image",
    unableCalculate: "Unable to calculate a formula.",
  },
  zh: {
    pageTitle: "Chromix — 色彩智能原型",
    pageDescription: "将产品照片转换为结合库存的数字调色配方。",
    status: "配色引擎在线",
    languageLabel: "语言",
    eyebrow: "色彩智能 / 制造业",
    heroTitleBefore: "从产品照片<br>到 ",
    heroTitleAccent: "调色配方。",
    heroDescription: "选择客户想要的颜色。使用现有材料估算配比，并将每种原料精确缩放到目标批次。",
    workflow: "工作流程",
    capture: "采集",
    analyze: "分析",
    formulate: "配方",
    colorCapture: "颜色采集",
    colorQuestion: "我们要调制什么颜色？",
    uploadImage: "上传产品图片",
    dropImage: "将产品图片拖到这里",
    browseImage: "或点击浏览 · PNG、JPG、WEBP",
    uploadedPreview: "已上传的产品预览",
    extractedPalette: "提取的色板",
    awaitingImage: "等待图片",
    paletteSource: "色板来源",
    fullFrame: "完整画面",
    selectRegion: "选择区域",
    selectionHelp: "选择色块、输入 HEX 值，或选择区域后开始配方。",
    targetColor: "目标颜色",
    copyColor: "复制颜色",
    copy: "复制",
    copied: "已复制",
    manualTarget: "手动目标",
    noImageTarget: "未选择图片目标",
    selectedAnalyzedRegion: "已从分析区域选择",
    selectedFullFrame: "已从完整画面色板选择",
    rgb: "RGB",
    rgbaHex: "RGBA 十六进制",
    lab: "LAB",
    calculatedOnMix: "将在配方计算后得出",
    formulationEstimate: "配方估算",
    buildPrototype: "建立原型配方。",
    productionBatch: "生产批次",
    totalRequiredMaterial: "所需材料总量",
    material: "材料",
    color: "颜色",
    available: "可用量",
    strength: "强度",
    costPerKg: "成本 / KG",
    materialName: "材料名称",
    materialColor: "材料颜色",
    availableKg: "可用千克数",
    relativeTintStrength: "相对着色强度",
    costPerKgLabel: "每千克成本",
    removeMaterial: "移除材料",
    addMaterial: "添加材料",
    newPigment: "新色料",
    materialNaturalResin: "天然树脂",
    materialCarbonBlack: "炭黑",
    materialSignalRed: "信号红",
    materialWarmYellow: "暖黄",
    materialUltramarine: "群青",
    calculateFormula: "计算配方",
    optimizing: "优化中…",
    ready: "就绪",
    target: "目标",
    predicted: "预测",
    colorDifference: "色差",
    runFormulation: "运行配方引擎，对比数字目标与预测混合色。",
    emptyRecipe: "原料配方将在这里显示。",
    totalBatch: "总批次",
    modelNote: "数字估算。生产配方需要使用实测材料样品进行校准。",
    lessTrial: "减少试错",
    lessTrialText: "在第一次实体打样前完成优化。",
    inventoryAware: "库存感知",
    inventoryAwareText: "只推荐现有库存中的材料。",
    scaleInstantly: "即时缩放",
    scaleInstantlyText: "从 1 kg 样品规划到大批量生产。",
    footerTagline: "色彩科学 × 材料智能",
    selectedRegionMeta: "选定区域",
    fullFrameMeta: "完整画面",
    pixels: "像素",
    regionHelp: "已分析选定区域。选择色块，或使用完整画面对比整张图片。",
    fullFrameHelp: "已显示完整画面色板。选择色块或选择区域；最大色簇不会自动选中。",
    uploadBeforeRegion: "请先上传图片，再选择区域。",
    dragRegion: "在图片中的产品区域上拖动，只分析该区域。",
    cancelRegion: "已取消区域选择。请选择色块或使用完整画面色板。",
    scoreClose: "在此数字模型中，视觉上非常接近。",
    scoreNoMatch: "在此数字模型中，当前库存无法完全复现目标颜色。",
    estimated: "预计",
    estimatedCost: "预计",
    estimatedTotal: "预计",
    qualityExcellent: "优秀",
    qualityGood: "良好",
    qualityApproximate: "近似",
    qualityNeedsCalibration: "需要校准",
    couldNotAnalyze: "无法分析图片",
    unableCalculate: "无法计算配方。",
  },
};

const localeFromUrl = new URLSearchParams(window.location.search).get("lang");
let currentLocale = ["en", "zh"].includes(localeFromUrl)
  ? localeFromUrl
  : (() => {
      try {
        return ["en", "zh"].includes(localStorage.getItem("chromix-locale"))
          ? localStorage.getItem("chromix-locale")
          : "en";
      } catch {
        return "en";
      }
    })();

function t(key) {
  return translations[currentLocale][key] ?? translations.en[key] ?? key;
}

function setLocale(locale) {
  if (!translations[locale] || locale === currentLocale) return;
  currentLocale = locale;
  try {
    localStorage.setItem("chromix-locale", locale);
  } catch {
    // Continue without persistence when storage is unavailable.
  }
  const url = new URL(window.location.href);
  url.searchParams.set("lang", locale);
  window.history.replaceState({}, "", url);
  applyTranslations();
}

const defaults = [
  { nameKey: "materialNaturalResin", color: "#EFE9DB", available: 230, strength: 1, cost: 1.45 },
  { nameKey: "materialCarbonBlack", color: "#121416", available: 12, strength: 10, cost: 5.20 },
  { nameKey: "materialSignalRed", color: "#D92F26", available: 18, strength: 10, cost: 7.10 },
  { nameKey: "materialWarmYellow", color: "#F2B92F", available: 15, strength: 8, cost: 6.85 },
  { nameKey: "materialUltramarine", color: "#214E9C", available: 15, strength: 8, cost: 7.40 },
];

function addMaterial(item = { nameKey: "newPigment", color: "#808080", available: 10, strength: 8, cost: 5 }) {
  if (materials.children.length >= 12) return;
  const name = item.name ?? t(item.nameKey ?? "newPigment");
  const row = document.createElement("div");
  row.className = "material-row";
  row.dataset.nameKey = item.nameKey ?? "";
  row.innerHTML = `
    <input class="mat-name" value="${escapeHtml(name)}" data-label-key="materialName" aria-label="${t("materialName")}">
    <input class="mat-color" type="color" value="${item.color}" data-label-key="materialColor" aria-label="${t("materialColor")}">
    <input class="mat-available" type="number" min="0" step="0.01" value="${item.available}" data-label-key="availableKg" aria-label="${t("availableKg")}">
    <input class="mat-strength" type="number" min="0.01" step="0.1" value="${item.strength}" data-label-key="relativeTintStrength" aria-label="${t("relativeTintStrength")}">
    <input class="mat-cost" type="number" min="0" step="0.01" value="${item.cost}" data-label-key="costPerKgLabel" aria-label="${t("costPerKgLabel")}">
    <button class="remove" type="button" data-i18n="removeMaterial" data-i18n-attribute="aria-label" aria-label="Remove material">×</button>`;
  row.querySelector(".mat-name").addEventListener("input", () => { row.dataset.nameKey = ""; });
  row.querySelector(".remove").addEventListener("click", () => {
    if (materials.children.length > 2) row.remove();
  });
  materials.appendChild(row);
}
defaults.forEach(addMaterial);
$("#addMaterial").addEventListener("click", () => addMaterial());

let currentFile = null;
let currentExtraction = null;
let selectionMode = false;
let roiStart = null;
let objectUrl = null;
let targetSelected = false;
let selectedTargetSource = "manual";
let selectedTargetPayload = null;
let displayedPaletteSource = "full_frame";
let lastResult = null;

function updateCalculateState() {
  $("#calculate").disabled = !targetSelected;
}

function setTarget(hex, payload = null, source = "manual") {
  if (!/^#[0-9A-F]{6}$/i.test(hex)) return;
  hex = hex.toUpperCase();
  selectedTargetPayload = payload;
  $("#targetHex").value = hex;
  $("#targetPicker").value = hex.toLowerCase();
  $("#targetVisual").style.background = hex;
  if (payload) {
    $("#colorMetrics").innerHTML = `
      <div><span>${t("rgb")}</span><b>${payload.rgb.join(", ")}</b></div>
      <div><span>${t("rgbaHex")}</span><b>${payload.hex8}</b></div>
      <div><span>${t("lab")}</span><b>${payload.lab.join(", ")}</b></div>`;
  } else {
    const rgb = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
    $("#colorMetrics").innerHTML = `<div><span>${t("rgb")}</span><b>${rgb.join(", ")}</b></div><div><span>${t("rgbaHex")}</span><b>${hex}FF</b></div><div><span>${t("lab")}</span><b>${t("calculatedOnMix")}</b></div>`;
  }
  selectedTargetSource = source;
  targetSelected = true;
  updateTargetSourceText();
  updateCalculateState();
}

function updateTargetSourceText() {
  $("#targetSource").textContent = selectedTargetSource === "roi"
    ? t("selectedAnalyzedRegion")
    : selectedTargetSource === "full_frame"
      ? t("selectedFullFrame")
      : t("manualTarget");
}

$("#targetPicker").addEventListener("input", e => setTarget(e.target.value, null, "manual"));
$("#targetHex").addEventListener("change", e => setTarget(e.target.value, null, "manual"));
$("#copyHex").addEventListener("click", async () => {
  await navigator.clipboard.writeText($("#targetHex").value);
  $("#copyHex").querySelector("span").textContent = t("copied");
  setTimeout(() => $("#copyHex").querySelector("span").textContent = t("copy"), 900);
});

const dropzone = $("#dropzone");
const imageInput = $("#imageInput");
const preview = $("#preview");
const roiSelection = $("#roiSelection");
const roiBox = $("#roiBox");
const fullFramePalette = $("#fullFramePalette");
const selectRegion = $("#selectRegion");
["dragenter", "dragover"].forEach(event => dropzone.addEventListener(event, e => { e.preventDefault(); dropzone.classList.add("drag"); }));
["dragleave", "drop"].forEach(event => dropzone.addEventListener(event, e => { e.preventDefault(); dropzone.classList.remove("drag"); }));
dropzone.addEventListener("drop", e => {
  if (!selectionMode) analyzeImage(e.dataTransfer.files[0]);
});
imageInput.addEventListener("change", e => analyzeImage(e.target.files[0]));
dropzone.addEventListener("keydown", e => {
  if (!selectionMode && (e.key === "Enter" || e.key === " ")) {
    e.preventDefault();
    imageInput.click();
  }
});

function setSelectionMode(active) {
  selectionMode = active;
  roiSelection.classList.toggle("active", active);
  roiSelection.setAttribute("aria-hidden", String(!active));
  selectRegion.classList.toggle("active", active || currentExtraction?.source === "roi");
  if (!active) roiStart = null;
}

function clearRoiBox() {
  roiSelection.classList.remove("has-box");
  roiBox.removeAttribute("style");
}

function imageBounds() {
  const imageWidth = currentExtraction?.original_width || preview.naturalWidth;
  const imageHeight = currentExtraction?.original_height || preview.naturalHeight;
  if (!imageWidth || !imageHeight) return null;
  const container = dropzone.getBoundingClientRect();
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

function selectionPoint(event, bounds) {
  return {
    x: Math.min(Math.max(event.clientX, bounds.left), bounds.left + bounds.width),
    y: Math.min(Math.max(event.clientY, bounds.top), bounds.top + bounds.height),
  };
}

function drawRoiBox(start, end, bounds) {
  const left = Math.min(start.x, end.x) - bounds.container.left;
  const top = Math.min(start.y, end.y) - bounds.container.top;
  const width = Math.abs(end.x - start.x);
  const height = Math.abs(end.y - start.y);
  roiBox.style.left = `${left}px`;
  roiBox.style.top = `${top}px`;
  roiBox.style.width = `${width}px`;
  roiBox.style.height = `${height}px`;
  roiSelection.classList.add("has-box");
}

roiSelection.addEventListener("pointerdown", event => {
  if (!selectionMode) return;
  const bounds = imageBounds();
  if (!bounds) return;
  roiStart = selectionPoint(event, bounds);
  drawRoiBox(roiStart, roiStart, bounds);
  roiSelection.setPointerCapture(event.pointerId);
  event.preventDefault();
});
roiSelection.addEventListener("pointermove", event => {
  if (!selectionMode || !roiStart) return;
  const bounds = imageBounds();
  if (bounds) drawRoiBox(roiStart, selectionPoint(event, bounds), bounds);
});
roiSelection.addEventListener("pointerup", event => {
  if (!selectionMode || !roiStart) return;
  const bounds = imageBounds();
  if (!bounds) return;
  const end = selectionPoint(event, bounds);
  const left = Math.min(roiStart.x, end.x);
  const top = Math.min(roiStart.y, end.y);
  const width = Math.abs(end.x - roiStart.x);
  const height = Math.abs(end.y - roiStart.y);
  if (width < 8 || height < 8) {
    clearRoiBox();
    setSelectionMode(true);
    return;
  }
  const scaleX = (currentExtraction?.original_width || preview.naturalWidth) / bounds.width;
  const scaleY = (currentExtraction?.original_height || preview.naturalHeight) / bounds.height;
  const roi = {
    x: Math.round((left - bounds.left) * scaleX),
    y: Math.round((top - bounds.top) * scaleY),
    width: Math.max(1, Math.round(width * scaleX)),
    height: Math.max(1, Math.round(height * scaleY)),
  };
  setSelectionMode(false);
  analyzeImage(currentFile, roi);
  event.preventDefault();
});

function renderPalette(colors, source) {
  displayedPaletteSource = source;
  const swatches = $("#swatches");
  swatches.innerHTML = "";
  colors.forEach(color => {
    const button = document.createElement("button");
    button.className = "swatch";
    button.style.background = color.hex;
    button.style.color = color.text_color;
    button.dataset.share = `${color.share}%`;
    button.title = `${t("targetColor")}: ${color.hex}`;
    button.addEventListener("click", () => setTarget(color.hex, color, source));
    swatches.appendChild(button);
  });
  fullFramePalette.classList.toggle("active", source === "full_frame");
  selectRegion.classList.toggle("active", source === "roi" || selectionMode);
}

function imageMetaText(data, source) {
  const sourceLabel = source === "roi" ? t("selectedRegionMeta") : t("fullFrameMeta");
  const palette = source === "roi" ? data : data.full_frame;
  return `${data.original_width} × ${data.original_height} · ${sourceLabel} · ${palette.analyzed_pixels.toLocaleString(currentLocale === "zh" ? "zh-CN" : "en-US")} ${t("pixels")}`;
}

function updateImageMeta(data) {
  const source = data.source === "roi" ? "roi" : "full_frame";
  $("#imageMeta").textContent = imageMetaText(data, source);
  $("#selectionHelp").textContent = source === "roi" ? t("regionHelp") : t("fullFrameHelp");
}

function showPalette(source) {
  if (!currentExtraction) return;
  const palette = source === "roi" ? currentExtraction.palette : currentExtraction.full_frame.palette;
  renderPalette(palette, source);
  $("#imageMeta").textContent = imageMetaText(currentExtraction, source);
  $("#selectionHelp").textContent = source === "roi" ? t("regionHelp") : t("fullFrameHelp");
}

function responseError(data, fallback) {
  if (Array.isArray(data.detail)) return data.detail[0]?.msg || fallback;
  if (data.detail && typeof data.detail === "object") return data.detail.message || fallback;
  return data.detail || fallback;
}

async function analyzeImage(file, roi = null) {
  if (!file) return;
  currentFile = file;
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  $("#errorMessage").textContent = "";
  objectUrl = URL.createObjectURL(file);
  preview.src = objectUrl;
  $("#targetSource").textContent = t("noImageTarget");
  targetSelected = false;
  selectedTargetSource = "manual";
  selectedTargetPayload = null;
  updateCalculateState();
  fullFramePalette.disabled = true;
  selectRegion.disabled = true;
  if (!roi) clearRoiBox();
  setSelectionMode(false);
  dropzone.classList.add("has-image", "loading");
  const form = new FormData();
  form.append("file", file);
  form.append("colors", "5");
  if (roi) {
    form.append("roi_x", roi.x);
    form.append("roi_y", roi.y);
    form.append("roi_width", roi.width);
    form.append("roi_height", roi.height);
  }
  try {
    const response = await fetch("/api/extract", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(responseError(data, t("couldNotAnalyze")));
    currentExtraction = data;
    renderPalette(data.palette, data.source);
    updateImageMeta(data);
    fullFramePalette.disabled = false;
    selectRegion.disabled = false;
  } catch (error) {
    $("#errorMessage").textContent = error.message;
  } finally {
    dropzone.classList.remove("loading");
  }
}

fullFramePalette.addEventListener("click", () => {
  if (!currentExtraction) return;
  setSelectionMode(false);
  clearRoiBox();
  showPalette("full_frame");
});

selectRegion.addEventListener("click", () => {
  if (!currentFile) {
    $("#selectionHelp").textContent = t("uploadBeforeRegion");
    return;
  }
  clearRoiBox();
  setSelectionMode(!selectionMode);
  $("#selectionHelp").textContent = selectionMode ? t("dragRegion") : t("cancelRegion");
});

$("#calculate").addEventListener("click", async () => {
  const button = $("#calculate");
  const error = $("#errorMessage");
  error.textContent = "";
  const payload = {
    target: $("#targetHex").value,
    target_source: selectedTargetSource,
    batch_kg: Number($("#batchMass").value),
    ingredients: [...materials.children].map(row => ({
      name: row.querySelector(".mat-name").value,
      color: row.querySelector(".mat-color").value,
      available_kg: Number(row.querySelector(".mat-available").value),
      strength: Number(row.querySelector(".mat-strength").value),
      cost_per_kg: Number(row.querySelector(".mat-cost").value),
    })),
  };
  button.disabled = true;
  button.querySelector("span").textContent = t("optimizing");
  try {
    const response = await fetch("/api/mix", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const data = await response.json();
    if (!response.ok) throw new Error(responseError(data, t("unableCalculate")));
    renderResult(data);
  } catch (err) {
    error.textContent = err.message || t("unableCalculate");
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = t("calculateFormula");
  }
});

function qualityText(quality) {
  const key = `quality${quality.replace(/\s+/g, "")}`;
  return t(key).toUpperCase();
}

function renderResult(data, scroll = true) {
  lastResult = data;
  $("#targetVisual").style.background = data.target.hex;
  $("#resultVisual").style.background = data.predicted.hex;
  $("#deltaE").textContent = `${data.delta_e_metric === "CIEDE2000" ? "ΔE00" : "ΔE"} ${data.delta_e.toFixed(2)}`;
  $("#quality").textContent = qualityText(data.quality);
  $("#scoreHelp").textContent = data.delta_e < 2 ? t("scoreClose") : t("scoreNoMatch");
  $("#recipe").innerHTML = data.recipe.filter(row => row.mass_kg > 0).map(row => `
    <div class="recipe-row"><i style="background:${row.color}"></i><div><b>${escapeHtml(row.name)}</b><span>${row.percentage.toFixed(3)}% · ${t("estimatedCost")} $${row.cost.toFixed(2)}</span></div><strong>${row.mass_kg.toFixed(4)} kg</strong></div>`).join("");
  const totalMass = data.total_mass_kg ?? data.batch_kg;
  $("#resultTotal").innerHTML = `<span>${t("totalBatch")} · ${t("estimatedTotal")} $${data.total_cost.toFixed(2)}</span><b>${totalMass.toFixed(4)} kg</b>`;
  if (scroll) $("#resultCard").scrollIntoView({ behavior: "smooth", block: "center" });
}

function escapeHtml(text) {
  const element = document.createElement("div");
  element.textContent = text;
  return element.innerHTML;
}

function applyTranslations() {
  document.documentElement.lang = currentLocale === "zh" ? "zh-CN" : "en";
  document.title = t("pageTitle");
  $("#pageDescription").content = t("pageDescription");
  document.querySelectorAll("[data-i18n]").forEach(element => {
    const value = t(element.dataset.i18n);
    const attribute = element.dataset.i18nAttribute;
    if (attribute) {
      element.setAttribute(attribute, value);
    } else if (element.dataset.i18nHtml === "true") {
      element.innerHTML = value;
    } else {
      element.textContent = value;
    }
  });
  document.querySelectorAll(".language-button").forEach(button => {
    const active = button.dataset.locale === currentLocale;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  document.querySelectorAll(".material-row").forEach(row => {
    if (row.dataset.nameKey) row.querySelector(".mat-name").value = t(row.dataset.nameKey);
    row.querySelectorAll("[data-label-key]").forEach(input => {
      input.setAttribute("aria-label", t(input.dataset.labelKey));
    });
  });
  if (targetSelected) {
    setTarget($("#targetHex").value, selectedTargetPayload, selectedTargetSource);
  } else if (currentFile) {
    $("#targetSource").textContent = t("noImageTarget");
  }
  if (currentExtraction) showPalette(displayedPaletteSource);
  if (lastResult) renderResult(lastResult, false);
}

function initializeLanguageControls() {
  document.querySelectorAll(".language-button").forEach(button => {
    button.addEventListener("click", event => {
      event.preventDefault();
      setLocale(button.dataset.locale);
    });
  });
  applyTranslations();
}

fullFramePalette.disabled = true;
selectRegion.disabled = true;
setTarget("#D8503F");
targetSelected = false;
updateCalculateState();
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeLanguageControls, { once: true });
} else {
  initializeLanguageControls();
}
