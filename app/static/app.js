import {
  createTargetWorkflow,
  imageBoundsFor,
  roiFromSelection,
  selectionPointFor,
} from "./target-workflow.mjs";

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
    whyTitle: "WHY THIS TARGET IS NOT MATCHED",
    whatToChange: "What to change",
    statusApproximate: "Approximated to within ΔE00 {delta_e}, not matched.",
    statusUnreachable: "Out of reach for this inventory — the closest mix is ΔE00 {delta_e} away.",
    reason_target_lighter_than_inventory:
      "No mixture of these materials can be this light. The target is L* {target_lightness}; the lightest reachable color is L* {inventory_max_lightness}.",
    reason_target_darker_than_inventory:
      "No mixture of these materials can be this dark. The target is L* {target_lightness}; the darkest reachable color is L* {inventory_min_lightness}.",
    reason_target_more_saturated_than_inventory:
      "The target is more saturated than these materials can mix to: chroma {target_chroma} requested, {reachable_chroma} reachable.",
    reason_target_hue_not_covered:
      "No material sits close enough to the target hue: the target is at {target_hue}°, the closest mix reaches {reachable_hue}°.",
    reason_outside_material_gamut:
      "Even with unlimited stock these materials only reach ΔE00 {material_gamut_delta_e} from the target.",
    reason_inventory_limited:
      "The closest recipe needs more material than is in stock; running out costs ΔE00 {penalty_delta_e}.",
    reason_constraints_limited:
      "The recipe constraints cost ΔE00 {penalty_delta_e} against an unconstrained mix ({active_constraints}).",
    reason_dispensing_granularity:
      "Rounding to the {scale_increment_kg} kg scale increment costs ΔE00 {penalty_delta_e}.",
    reason_model_fit_limit:
      "The closest mix is ΔE00 {delta_e} from the target; no single restriction explains the gap.",
    suggestion_add_lighter_base: "Add a white or opaque base lighter than L* {required_lightness}.",
    suggestion_add_darker_material: "Add a black or deep tinting material to the inventory.",
    suggestion_add_saturated_pigment:
      "Add a stronger pigment near hue {target_hue}°, or reduce the amount of uncolored base the recipe has to tint.",
    suggestion_add_hue_pigment: "Add a pigment near hue {target_hue}°.",
    suggestion_add_material: "Add a material closer to the target color.",
    suggestion_restock_materials: "Restock {materials}.",
    suggestion_restock_generic: "Increase the available material quantities.",
    suggestion_relax_constraints: "Relax the {constraint} to let the optimizer use a closer mix.",
    constraint_minimum_dose: "minimum dose",
    constraint_ingredient_count: "ingredient count limit",
    constraint_mutual_exclusivity: "mutually exclusive materials",
    constraint_locked_materials: "locked materials",
    constraint_correction_doses: "fixed correction doses",
    suggestion_finer_scale: "Use a finer scale increment than {scale_increment_kg} kg, or mix a larger batch.",
    exhaustedMaterials: "Fully consumed: {materials}.",
    listSeparator: ", ",
    error_empty_upload: "The uploaded image is empty.",
    error_upload_too_large: "Image is larger than the 12 MB demo limit.",
    error_undecodable_image: "Upload a valid PNG, JPG, or WebP image.",
    error_unsupported_format: "Decoded image format {format} is not supported; use {supported}.",
    error_image_too_large: "Image dimensions are too large.",
    error_icc_conversion_failed: "The embedded ICC profile could not be converted to sRGB.",
    error_no_visible_pixels: "The image contains no visible pixels.",
    error_roi_incomplete: "A region needs x, y, width, and height.",
    error_roi_invalid: "Region coordinates and dimensions must be positive.",
    error_roi_outside_image: "The selected region must fit inside the uploaded image.",
    error_batch_out_of_range: "Batch mass must be greater than 0 and no more than 1,000,000 kg.",
    error_too_few_materials: "Add at least two available materials.",
    error_invalid_material_values: "Mass and cost cannot be negative, and tint strength must be positive.",
    error_insufficient_inventory: "Only {available_kg} kg is available for a {batch_kg} kg batch.",
    error_duplicate_material_names: "Material names must be unique.",
    error_invalid_scale_increment: "The scale increment must be positive and no greater than the batch.",
    error_invalid_minimum_dose: "The minimum dose must be finite and nonnegative.",
    error_invalid_ingredient_count: "The ingredient count limit is outside the available material range.",
    error_invalid_color_tolerance: "The color tolerance must be finite and nonnegative.",
    error_unknown_constraint_material: "A constraint references an unknown material: {material}.",
    error_exclusive_group_too_small: "A mutually exclusive group needs at least two distinct materials.",
    error_exclusive_groups_overlap: "Mutually exclusive groups cannot share a material.",
    error_locked_materials_exclusive: "Locked materials cannot be mutually exclusive.",
    error_correction_repeats_material: "A correction recipe cannot repeat a material.",
    error_invalid_correction_mass: "Correction recipe masses must be finite and nonnegative.",
    error_correction_not_on_scale: "Correction recipe masses must use the configured scale increment.",
    error_correction_exceeds_inventory: "The correction recipe exceeds the inventory for {material}.",
    error_correction_exceeds_batch: "The correction recipe exceeds the requested batch mass.",
    error_correction_below_minimum: "The correction recipe is below the minimum dose for {material}.",
    error_locked_material_needs_dose: "Locked material {material} needs a positive correction dose.",
    error_ingredient_count_below_minimum:
      "A {batch_kg} kg batch needs at least {minimum_materials} materials, but the recipe is limited to {count}: the {count} largest stocks hold only {held_kg} kg. Raise the ingredient count limit or restock.",
    error_minimum_dose_strands_materials:
      "A {minimum_dose_kg} kg minimum dose leaves only {dosable} of {total} materials usable, holding {usable_kg} kg for a {batch_kg} kg batch. Lower the minimum dose or restock.",
    error_minimum_dose_exceeds_batch:
      "A {minimum_dose_kg} kg minimum dose cannot fit a {batch_kg} kg batch: it needs at least {minimum_materials} materials, or {required_kg} kg of minimum doses. Lower the minimum dose or mix a larger batch.",
    error_locked_minimum_exceeds_batch:
      "The {locked} locked or correction materials each need at least {minimum_dose_kg} kg, which exceeds the {batch_kg} kg batch. Unlock a material or lower the minimum dose.",
    error_exclusive_groups_starve_batch:
      "The mutually exclusive groups leave only {usable_kg} kg usable for a {batch_kg} kg batch, because only one material per group may be dosed.",
    error_no_feasible_combination: "No combination of materials satisfies the requested constraints.",
    error_no_feasible_recipe: "The formulation optimizer could not find a workable recipe.",
    error_formulation_busy: "The formulation engine is busy. Please try again in a few seconds.",
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
    whyTitle: "为什么无法匹配该目标",
    whatToChange: "改进建议",
    statusApproximate: "只能近似到 ΔE00 {delta_e}，并非精确匹配。",
    statusUnreachable: "当前库存无法达到该目标——最接近的混合色相差 ΔE00 {delta_e}。",
    reason_target_lighter_than_inventory:
      "这些材料的任何混合都无法这么浅。目标为 L* {target_lightness}，可达到的最浅颜色为 L* {inventory_max_lightness}。",
    reason_target_darker_than_inventory:
      "这些材料的任何混合都无法这么深。目标为 L* {target_lightness}，可达到的最深颜色为 L* {inventory_min_lightness}。",
    reason_target_more_saturated_than_inventory:
      "目标的饱和度超出这些材料的混合能力：需要彩度 {target_chroma}，可达到 {reachable_chroma}。",
    reason_target_hue_not_covered:
      "没有材料的色相足够接近目标：目标位于 {target_hue}°，最接近的混合色只能达到 {reachable_hue}°。",
    reason_outside_material_gamut:
      "即使库存不受限，这些材料与目标仍相差 ΔE00 {material_gamut_delta_e}。",
    reason_inventory_limited:
      "最接近的配方所需材料超出库存；库存不足导致 ΔE00 {penalty_delta_e} 的误差。",
    reason_constraints_limited:
      "与无约束混合相比，配方约束（{active_constraints}）导致 ΔE00 {penalty_delta_e} 的误差。",
    reason_dispensing_granularity:
      "按 {scale_increment_kg} kg 的称量步进取整导致 ΔE00 {penalty_delta_e} 的误差。",
    reason_model_fit_limit:
      "最接近的混合色与目标相差 ΔE00 {delta_e}；没有单一限制可以解释该差距。",
    suggestion_add_lighter_base: "添加比 L* {required_lightness} 更浅的白色或遮盖性基料。",
    suggestion_add_darker_material: "在库存中添加黑色或深色着色材料。",
    suggestion_add_saturated_pigment:
      "在 {target_hue}° 色相附近添加着色力更强的颜料，或减少配方需要着色的无色基料用量。",
    suggestion_add_hue_pigment: "在 {target_hue}° 色相附近添加颜料。",
    suggestion_add_material: "添加更接近目标颜色的材料。",
    suggestion_restock_materials: "补充以下材料：{materials}。",
    suggestion_restock_generic: "增加可用材料的库存量。",
    suggestion_relax_constraints: "放宽“{constraint}”，让优化器可以使用更接近的混合方案。",
    constraint_minimum_dose: "最小用量",
    constraint_ingredient_count: "材料数量上限",
    constraint_mutual_exclusivity: "互斥材料",
    constraint_locked_materials: "锁定材料",
    constraint_correction_doses: "固定校正用量",
    suggestion_finer_scale: "使用比 {scale_increment_kg} kg 更精细的称量步进，或调制更大的批次。",
    exhaustedMaterials: "已全部用完：{materials}。",
    listSeparator: "、",
    error_empty_upload: "上传的图片为空。",
    error_upload_too_large: "图片超过 12 MB 的演示上限。",
    error_undecodable_image: "请上传有效的 PNG、JPG 或 WebP 图片。",
    error_unsupported_format: "不支持解码后的图片格式 {format}；请使用 {supported}。",
    error_image_too_large: "图片尺寸过大。",
    error_icc_conversion_failed: "无法将内嵌的 ICC 配置文件转换为 sRGB。",
    error_no_visible_pixels: "图片中没有可见像素。",
    error_roi_incomplete: "选择区域需要 x、y、宽度和高度。",
    error_roi_invalid: "区域的坐标和尺寸必须为正数。",
    error_roi_outside_image: "所选区域必须位于上传的图片范围内。",
    error_batch_out_of_range: "批次质量必须大于 0 且不超过 1,000,000 kg。",
    error_too_few_materials: "请至少添加两种可用材料。",
    error_invalid_material_values: "质量和成本不能为负，着色强度必须为正数。",
    error_insufficient_inventory: "库存仅有 {available_kg} kg，无法满足 {batch_kg} kg 的批次。",
    error_duplicate_material_names: "材料名称不能重复。",
    error_invalid_scale_increment: "称量步进必须为正数，且不得大于批次质量。",
    error_invalid_minimum_dose: "最小用量必须为有限的非负数。",
    error_invalid_ingredient_count: "材料数量上限超出了可用材料的范围。",
    error_invalid_color_tolerance: "颜色容差必须为有限的非负数。",
    error_unknown_constraint_material: "约束条件引用了未知材料：{material}。",
    error_exclusive_group_too_small: "互斥分组至少需要两种不同的材料。",
    error_exclusive_groups_overlap: "互斥分组之间不能包含相同的材料。",
    error_locked_materials_exclusive: "锁定的材料不能互斥。",
    error_correction_repeats_material: "校正配方中不能重复同一种材料。",
    error_invalid_correction_mass: "校正配方的质量必须为有限的非负数。",
    error_correction_not_on_scale: "校正配方的质量必须符合所设置的称量步进。",
    error_correction_exceeds_inventory: "校正配方超出了 {material} 的库存。",
    error_correction_exceeds_batch: "校正配方超出了请求的批次质量。",
    error_correction_below_minimum: "校正配方低于 {material} 的最小用量。",
    error_locked_material_needs_dose: "锁定材料 {material} 需要一个正的校正用量。",
    error_ingredient_count_below_minimum:
      "{batch_kg} kg 的批次至少需要 {minimum_materials} 种材料，但配方被限制为 {count} 种：库存最多的 {count} 种材料仅有 {held_kg} kg。请提高材料数量上限或补充库存。",
    error_minimum_dose_strands_materials:
      "{minimum_dose_kg} kg 的最小用量使 {total} 种材料中只有 {dosable} 种可用，共 {usable_kg} kg，无法满足 {batch_kg} kg 的批次。请降低最小用量或补充库存。",
    error_minimum_dose_exceeds_batch:
      "{minimum_dose_kg} kg 的最小用量无法容纳于 {batch_kg} kg 的批次：至少需要 {minimum_materials} 种材料，即 {required_kg} kg 的最小用量。请降低最小用量或调制更大的批次。",
    error_locked_minimum_exceeds_batch:
      "{locked} 种锁定或校正材料各自至少需要 {minimum_dose_kg} kg，已超出 {batch_kg} kg 的批次。请解锁材料或降低最小用量。",
    error_exclusive_groups_starve_batch:
      "互斥分组使可用材料仅剩 {usable_kg} kg，无法满足 {batch_kg} kg 的批次，因为每组只能使用一种材料。",
    error_no_feasible_combination: "没有任何材料组合能够满足所设置的约束条件。",
    error_no_feasible_recipe: "配方优化器未能找到可行的配方。",
    error_formulation_busy: "配方引擎正忙，请稍等几秒后重试。",
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
let objectUrl = null;
let lastResult = null;
const targetWorkflow = createTargetWorkflow();

function updateCalculateState() {
  $("#calculate").disabled = !targetWorkflow.snapshot().targetSelected;
}

function setTarget(hex, payload = null, source = "manual") {
  if (!/^#[0-9A-F]{6}$/i.test(hex)) return;
  hex = hex.toUpperCase();
  targetWorkflow.selectTarget(source, payload);
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
  updateTargetSourceText();
  updateCalculateState();
}

function updateTargetSourceText() {
  const { selectedTargetSource } = targetWorkflow.snapshot();
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
  if (!targetWorkflow.snapshot().selectionMode) analyzeImage(e.dataTransfer.files[0]);
});
imageInput.addEventListener("change", e => analyzeImage(e.target.files[0]));
dropzone.addEventListener("keydown", e => {
  if (!targetWorkflow.snapshot().selectionMode && (e.key === "Enter" || e.key === " ")) {
    e.preventDefault();
    imageInput.click();
  }
});

function setSelectionMode(active) {
  const state = targetWorkflow.setSelectionMode(active);
  roiSelection.classList.toggle("active", active);
  roiSelection.setAttribute("aria-hidden", String(!active));
  selectRegion.classList.toggle("active", active || currentExtraction?.source === "roi");
  return state;
}

function clearRoiBox() {
  roiSelection.classList.remove("has-box");
  roiBox.removeAttribute("style");
}

function imageBounds() {
  const imageWidth = currentExtraction?.original_width || preview.naturalWidth;
  const imageHeight = currentExtraction?.original_height || preview.naturalHeight;
  const container = dropzone.getBoundingClientRect();
  return imageBoundsFor(imageWidth, imageHeight, container);
}

function selectionPoint(event, bounds) {
  return selectionPointFor(event, bounds);
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
  if (!targetWorkflow.snapshot().selectionMode) return;
  const bounds = imageBounds();
  if (!bounds) return;
  const roiStart = targetWorkflow.setRoiStart(selectionPoint(event, bounds)).roiStart;
  drawRoiBox(roiStart, roiStart, bounds);
  roiSelection.setPointerCapture(event.pointerId);
  event.preventDefault();
});
roiSelection.addEventListener("pointermove", event => {
  const state = targetWorkflow.snapshot();
  if (!state.selectionMode || !state.roiStart) return;
  const bounds = imageBounds();
  if (bounds) drawRoiBox(state.roiStart, selectionPoint(event, bounds), bounds);
});
roiSelection.addEventListener("pointerup", event => {
  const state = targetWorkflow.snapshot();
  if (!state.selectionMode || !state.roiStart) return;
  const bounds = imageBounds();
  if (!bounds) return;
  const end = selectionPoint(event, bounds);
  const imageWidth = currentExtraction?.original_width || preview.naturalWidth;
  const imageHeight = currentExtraction?.original_height || preview.naturalHeight;
  const roi = roiFromSelection(state.roiStart, end, bounds, imageWidth, imageHeight);
  if (!roi) {
    clearRoiBox();
    setSelectionMode(true);
    return;
  }
  setSelectionMode(false);
  analyzeImage(currentFile, roi);
  event.preventDefault();
});

function renderPalette(colors, source) {
  targetWorkflow.setDisplayedPaletteSource(source);
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
  selectRegion.classList.toggle("active", source === "roi" || targetWorkflow.snapshot().selectionMode);
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
  if (data.detail && typeof data.detail === "object") {
    // Prefer the localized template for the coded cause; the API message is
    // always English and is only the fallback.
    const key = `error_${data.detail.reason_code}`;
    const template = translations[currentLocale][key] ?? translations.en[key];
    if (template) return fillTemplate(template, data.detail.reason_params);
    return data.detail.message || fallback;
  }
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
  targetWorkflow.resetForNewImage();
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
  const selectionMode = !targetWorkflow.snapshot().selectionMode;
  setSelectionMode(selectionMode);
  $("#selectionHelp").textContent = selectionMode ? t("dragRegion") : t("cancelRegion");
});

$("#calculate").addEventListener("click", async () => {
  const button = $("#calculate");
  const error = $("#errorMessage");
  error.textContent = "";
  const { selectedTargetSource } = targetWorkflow.snapshot();
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

function fillTemplate(template, params = {}) {
  return template.replace(/\{(\w+)\}/g, (match, name) => {
    const value = params[name];
    if (value === undefined || value === null) return match;
    return Array.isArray(value) ? value.join(t("listSeparator")) : String(value);
  });
}

// Reasons carry a stable code plus parameters so both locales can explain the
// same finding; the English message from the API is the fallback.
function explanationText(entry) {
  const key = `${entry.kind}_${entry.code}`;
  const template = translations[currentLocale][key] ?? translations.en[key];
  if (!template) return entry.message;
  // Constraint identifiers arrive as codes so they can be named in either language.
  const params = { ...entry.params };
  if (Array.isArray(params.active_constraints)) {
    params.active_constraints = params.active_constraints.map(code => t(`constraint_${code}`));
  }
  if (params.constraint) params.constraint = t(`constraint_${params.constraint}`);
  return fillTemplate(template, params);
}

function renderReachability(data) {
  const panel = $("#reachability");
  const reachability = data.target_reachability;
  if (!reachability || reachability.status === "reachable") {
    panel.hidden = true;
    panel.innerHTML = "";
    return;
  }
  const statusKey = reachability.status === "unreachable" ? "statusUnreachable" : "statusApproximate";
  const reasons = reachability.reasons.map(item => {
    const exhausted = item.params && item.params.exhausted_materials;
    const extra = exhausted && exhausted.length
      ? ` ${fillTemplate(t("exhaustedMaterials"), { materials: exhausted.map(escapeHtml) })}`
      : "";
    return `<li>${escapeHtml(explanationText({ ...item, kind: "reason" }))}${extra}</li>`;
  }).join("");
  const suggestions = reachability.suggestions
    .map(item => `<li>${escapeHtml(explanationText({ ...item, kind: "suggestion" }))}</li>`)
    .join("");
  panel.innerHTML = `
    <div class="why-head"><span>${escapeHtml(t("whyTitle"))}</span></div>
    <p class="why-status">${escapeHtml(fillTemplate(t(statusKey), { delta_e: reachability.delta_e.toFixed(2) }))}</p>
    <ul class="why-list">${reasons}</ul>
    ${suggestions ? `<div class="why-head"><span>${escapeHtml(t("whatToChange"))}</span></div><ul class="why-list why-fix">${suggestions}</ul>` : ""}`;
  panel.hidden = false;
}

function renderResult(data, scroll = true) {
  lastResult = data;
  $("#targetVisual").style.background = data.target.hex;
  $("#resultVisual").style.background = data.predicted.hex;
  $("#deltaE").textContent = `${data.delta_e_metric === "CIEDE2000" ? "ΔE00" : "ΔE"} ${data.delta_e.toFixed(2)}`;
  $("#quality").textContent = qualityText(data.quality);
  $("#scoreHelp").textContent = data.delta_e < 2 ? t("scoreClose") : t("scoreNoMatch");
  renderReachability(data);
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
  const state = targetWorkflow.snapshot();
  if (state.targetSelected) {
    setTarget($("#targetHex").value, state.selectedTargetPayload, state.selectedTargetSource);
  } else if (currentFile) {
    $("#targetSource").textContent = t("noImageTarget");
  }
  if (currentExtraction) showPalette(state.displayedPaletteSource);
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
targetWorkflow.resetForNewImage();
updateCalculateState();
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeLanguageControls, { once: true });
} else {
  initializeLanguageControls();
}
