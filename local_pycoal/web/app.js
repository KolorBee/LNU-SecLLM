const sourcePreview = document.getElementById("source-preview");
const resultPreview = document.getElementById("result-preview");
const sourceEmpty = document.getElementById("source-empty");
const resultEmpty = document.getElementById("result-empty");
const sceneLabel = document.getElementById("scene-label");
const inputModeSelect = document.getElementById("input-mode");
const workflowSelect = document.getElementById("workflow-select");
const imagePathInput = document.getElementById("image-path");
const imageHdrFileInput = document.getElementById("image-hdr-file");
const imageImgFileInput = document.getElementById("image-img-file");
const libraryPathInput = document.getElementById("library-path");
const configPathInput = document.getElementById("config-path");
const libraryHdrFileInput = document.getElementById("library-hdr-file");
const libraryImgFileInput = document.getElementById("library-img-file");
const configFileInput = document.getElementById("config-file");
const spectralVersionSelect = document.getElementById("spectral-version");
const pathFields = document.getElementById("path-fields");
const uploadFields = document.getElementById("upload-fields");
const mineralFields = document.getElementById("mineral-fields");
const miningFields = document.getElementById("mining-fields");
const mineralUploadFields = document.getElementById("mineral-upload-fields");
const runButton = document.getElementById("run-button");
const statusText = document.getElementById("status-text");
const loadMineralDemoButton = document.getElementById("load-mineral-demo");
const loadMiningDemoButton = document.getElementById("load-mining-demo");
const summaryScene = document.getElementById("summary-scene");
const summaryWorkflow = document.getElementById("summary-workflow");
const summarySource = document.getElementById("summary-source");
const summaryResult = document.getElementById("summary-result");
const summaryOutput = document.getElementById("summary-output");
const swapButton = document.getElementById("swap-button");

let defaults = null;

function updateSummary() {
  summaryScene.textContent = sceneLabel.value.trim() || "Not set";
  summaryWorkflow.textContent = workflowSelect.options[workflowSelect.selectedIndex].text;
}

function showPreview(url, imageNode, emptyNode, summaryNode, label) {
  if (!url) {
    return;
  }

  imageNode.src = `${url}?t=${Date.now()}`;
  imageNode.hidden = false;
  emptyNode.hidden = true;
  summaryNode.textContent = label;
}

function applyDefaults(workflow) {
  if (!defaults) {
    return;
  }

  if (workflow === "mineral") {
    imagePathInput.value = defaults.mineral.image_path;
    libraryPathInput.value = defaults.mineral.library_path;
    configPathInput.value = defaults.mineral.config_path;
    sceneLabel.value = "AVIRIS mineral demo";
  } else {
    imagePathInput.value = defaults.mining.image_path;
    spectralVersionSelect.value = defaults.mining.spectral_version;
    sceneLabel.value = "AVIRIS mining demo";
  }

  updateSummary();
}

function updateWorkflowFields() {
  const workflow = workflowSelect.value;
  const inputMode = inputModeSelect.value;
  mineralFields.hidden = workflow !== "mineral";
  miningFields.hidden = workflow !== "mining";
  pathFields.hidden = inputMode !== "path";
  uploadFields.hidden = inputMode !== "upload";
  mineralUploadFields.hidden = !(workflow === "mineral" && inputMode === "upload");
  updateSummary();
}

async function loadDefaults() {
  const response = await fetch("/api/defaults");
  defaults = await response.json();
  applyDefaults(workflowSelect.value);
}

function appendIfPresent(formData, key, fileInput) {
  if (fileInput.files.length > 0) {
    formData.append(key, fileInput.files[0]);
  }
}

async function runPipeline() {
  const workflow = workflowSelect.value;
  const inputMode = inputModeSelect.value;

  runButton.disabled = true;
  statusText.textContent = "Running Pycoal backend job...";
  summaryOutput.textContent = "Running...";

  try {
    let response;
    if (inputMode === "upload") {
      const formData = new FormData();
      formData.append("workflow", workflow);
      appendIfPresent(formData, "image_hdr", imageHdrFileInput);
      appendIfPresent(formData, "image_img", imageImgFileInput);

      if (workflow === "mineral") {
        if (libraryPathInput.value.trim()) {
          formData.append("library_path", libraryPathInput.value.trim());
        }
        if (configPathInput.value.trim()) {
          formData.append("config_path", configPathInput.value.trim());
        }
        appendIfPresent(formData, "library_hdr", libraryHdrFileInput);
        appendIfPresent(formData, "library_img", libraryImgFileInput);
        appendIfPresent(formData, "config_file", configFileInput);
      } else {
        formData.append("spectral_version", spectralVersionSelect.value);
      }

      response = await fetch("/api/run-upload", {
        method: "POST",
        body: formData,
      });
    } else {
      const payload = {
        workflow,
        image_path: imagePathInput.value.trim(),
      };

      if (workflow === "mineral") {
        payload.library_path = libraryPathInput.value.trim();
        payload.config_path = configPathInput.value.trim();
      } else {
        payload.spectral_version = spectralVersionSelect.value;
      }

      response = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }

    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || "Unknown backend error.");
    }

    showPreview(data.source_preview_url, sourcePreview, sourceEmpty, summarySource, data.input_path);
    showPreview(data.result_preview_url, resultPreview, resultEmpty, summaryResult, data.result_path);
    summaryOutput.textContent = data.result_path;
    statusText.textContent = `Completed ${data.workflow} workflow.`;
  } catch (error) {
    statusText.textContent = `Run failed: ${error.message}`;
    summaryOutput.textContent = "Run failed";
  } finally {
    runButton.disabled = false;
  }
}

sceneLabel.addEventListener("input", updateSummary);
inputModeSelect.addEventListener("change", updateWorkflowFields);
workflowSelect.addEventListener("change", () => {
  updateWorkflowFields();
  applyDefaults(workflowSelect.value);
});
runButton.addEventListener("click", runPipeline);
loadMineralDemoButton.addEventListener("click", () => {
  workflowSelect.value = "mineral";
  updateWorkflowFields();
  applyDefaults("mineral");
});
loadMiningDemoButton.addEventListener("click", () => {
  workflowSelect.value = "mining";
  updateWorkflowFields();
  applyDefaults("mining");
});

swapButton.addEventListener("click", () => {
  const sourceSrc = sourcePreview.src;
  const resultSrc = resultPreview.src;
  const sourceVisible = !sourcePreview.hidden;
  const resultVisible = !resultPreview.hidden;
  const sourceName = summarySource.textContent;
  const resultName = summaryResult.textContent;
  const outputName = summaryOutput.textContent;

  sourcePreview.src = resultSrc;
  resultPreview.src = sourceSrc;
  sourcePreview.hidden = !resultVisible;
  resultPreview.hidden = !sourceVisible;
  sourceEmpty.hidden = resultVisible;
  resultEmpty.hidden = sourceVisible;
  summarySource.textContent = resultName;
  summaryResult.textContent = sourceName;
  summaryOutput.textContent = outputName;
});

updateWorkflowFields();
loadDefaults().catch((error) => {
  statusText.textContent = `Could not load backend defaults: ${error.message}`;
});