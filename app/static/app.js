const $ = (selector) => document.querySelector(selector);
const materials = $("#materials");
const defaults = [
  { name: "Natural resin", color: "#EFE9DB", available: 230, strength: 1, cost: 1.45 },
  { name: "Carbon black", color: "#121416", available: 12, strength: 10, cost: 5.20 },
  { name: "Signal red", color: "#D92F26", available: 18, strength: 10, cost: 7.10 },
  { name: "Warm yellow", color: "#F2B92F", available: 15, strength: 8, cost: 6.85 },
  { name: "Ultramarine", color: "#214E9C", available: 15, strength: 8, cost: 7.40 },
];

function addMaterial(item = { name: "New pigment", color: "#808080", available: 10, strength: 8, cost: 5 }) {
  if (materials.children.length >= 12) return;
  const row = document.createElement("div");
  row.className = "material-row";
  row.innerHTML = `
    <input class="mat-name" value="${item.name}" aria-label="Material name">
    <input class="mat-color" type="color" value="${item.color}" aria-label="Material color">
    <input class="mat-available" type="number" min="0" step="0.01" value="${item.available}" aria-label="Available kilograms">
    <input class="mat-strength" type="number" min="0.01" step="0.1" value="${item.strength}" aria-label="Relative tint strength">
    <input class="mat-cost" type="number" min="0" step="0.01" value="${item.cost}" aria-label="Cost per kilogram">
    <button class="remove" type="button" aria-label="Remove material">×</button>`;
  row.querySelector(".remove").addEventListener("click", () => {
    if (materials.children.length > 2) row.remove();
  });
  materials.appendChild(row);
}
defaults.forEach(addMaterial);
$("#addMaterial").addEventListener("click", () => addMaterial());

function setTarget(hex, payload = null) {
  if (!/^#[0-9A-F]{6}$/i.test(hex)) return;
  hex = hex.toUpperCase();
  $("#targetHex").value = hex;
  $("#targetPicker").value = hex.toLowerCase();
  $("#targetVisual").style.background = hex;
  if (payload) {
    $("#colorMetrics").innerHTML = `
      <div><span>RGB</span><b>${payload.rgb.join(", ")}</b></div>
      <div><span>RGBA HEX</span><b>${payload.hex8}</b></div>
      <div><span>LAB</span><b>${payload.lab.join(", ")}</b></div>`;
  } else {
    const rgb = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
    $("#colorMetrics").innerHTML = `<div><span>RGB</span><b>${rgb.join(", ")}</b></div><div><span>RGBA HEX</span><b>${hex}FF</b></div><div><span>LAB</span><b>Calculated on mix</b></div>`;
  }
}

$("#targetPicker").addEventListener("input", e => setTarget(e.target.value));
$("#targetHex").addEventListener("change", e => setTarget(e.target.value));
$("#copyHex").addEventListener("click", async () => {
  await navigator.clipboard.writeText($("#targetHex").value);
  $("#copyHex").textContent = "COPIED";
  setTimeout(() => $("#copyHex").textContent = "COPY", 900);
});

const dropzone = $("#dropzone");
const imageInput = $("#imageInput");
["dragenter", "dragover"].forEach(event => dropzone.addEventListener(event, e => { e.preventDefault(); dropzone.classList.add("drag"); }));
["dragleave", "drop"].forEach(event => dropzone.addEventListener(event, e => { e.preventDefault(); dropzone.classList.remove("drag"); }));
dropzone.addEventListener("drop", e => analyzeImage(e.dataTransfer.files[0]));
imageInput.addEventListener("change", e => analyzeImage(e.target.files[0]));

async function analyzeImage(file) {
  if (!file) return;
  $("#errorMessage").textContent = "";
  const objectUrl = URL.createObjectURL(file);
  $("#preview").src = objectUrl;
  dropzone.classList.add("has-image", "loading");
  const form = new FormData();
  form.append("file", file);
  form.append("colors", "5");
  try {
    const response = await fetch("/api/extract", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not analyze the image");
    $("#imageMeta").textContent = `${data.width} × ${data.height} · ${data.analyzed_pixels.toLocaleString()} px`;
    const swatches = $("#swatches");
    swatches.innerHTML = "";
    data.palette.forEach(color => {
      const button = document.createElement("button");
      button.className = "swatch";
      button.style.background = color.hex;
      button.style.color = color.text_color;
      button.dataset.share = `${color.share}%`;
      button.title = `Use ${color.hex}`;
      button.addEventListener("click", () => setTarget(color.hex, color));
      swatches.appendChild(button);
    });
    setTarget(data.dominant.hex, data.dominant);
  } catch (error) {
    $("#errorMessage").textContent = error.message;
  } finally {
    dropzone.classList.remove("loading");
  }
}

$("#calculate").addEventListener("click", async () => {
  const button = $("#calculate");
  const error = $("#errorMessage");
  error.textContent = "";
  const payload = {
    target: $("#targetHex").value,
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
  button.querySelector("span").textContent = "OPTIMIZING…";
  try {
    const response = await fetch("/api/mix", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const data = await response.json();
    if (!response.ok) throw new Error(Array.isArray(data.detail) ? data.detail[0].msg : data.detail);
    renderResult(data);
  } catch (err) {
    error.textContent = err.message || "Unable to calculate a formula.";
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = "CALCULATE FORMULA";
  }
});

function renderResult(data) {
  $("#targetVisual").style.background = data.target.hex;
  $("#resultVisual").style.background = data.predicted.hex;
  $("#deltaE").textContent = `ΔE ${data.delta_e.toFixed(2)}`;
  $("#quality").textContent = data.quality.toUpperCase();
  $("#scoreHelp").textContent = data.delta_e < 2 ? "Visually very close in this digital model." : "The current inventory cannot reproduce the target exactly in this digital model.";
  $("#recipe").innerHTML = data.recipe.filter(row => row.mass_kg > 0).map(row => `
    <div class="recipe-row"><i style="background:${row.color}"></i><div><b>${escapeHtml(row.name)}</b><span>${row.percentage.toFixed(3)}% · est. $${row.cost.toFixed(2)}</span></div><strong>${row.mass_kg.toFixed(4)} kg</strong></div>`).join("");
  $("#resultTotal").innerHTML = `<span>TOTAL BATCH · EST. $${data.total_cost.toFixed(2)}</span><b>${data.batch_kg.toFixed(3)} kg</b>`;
  $("#resultCard").scrollIntoView({ behavior: "smooth", block: "center" });
}

function escapeHtml(text) {
  const element = document.createElement("div");
  element.textContent = text;
  return element.innerHTML;
}

setTarget("#D8503F");
