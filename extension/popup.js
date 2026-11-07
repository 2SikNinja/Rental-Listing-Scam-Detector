/**
 * Popup logic: read the current tab (only on click), let the user review,
 * send to the API, and show the result.
 *
 * Security notes:
 *   - Page text and API responses are untrusted. They are only ever put on
 *     the screen with textContent, never innerHTML, so a malicious listing
 *     can't inject scripts into the extension.
 *   - The extension can only read the page after the user clicks (activeTab),
 *     and can only send data to the API listed in manifest.json.
 */

import { apiBaseUrl, privacyPolicyUrl, requestTimeoutMs } from "./config.js";
import { extractListing } from "./extractListing.js";

const elements = Object.fromEntries(
  [
    "startSection", "readPageButton", "privacyLink", "reviewForm", "titleInput", "descriptionInput",
    "rentInput", "bedroomsInput", "streetInput", "cityInput", "stateInput", "zipInput", "extractionNote",
    "analyzeButton", "statusMessage", "resultSection",
  ].map((elementId) => [elementId, document.getElementById(elementId)]),
);

const riskLabels = {
  high: "High risk",
  medium: "Medium risk",
  low: "Low risk",
  insufficient_data: "Not enough information",
};

let pageUrl = null;

elements.privacyLink.href = privacyPolicyUrl;

function showStatus(message) {
  elements.statusMessage.textContent = message;
  elements.statusMessage.hidden = !message;
}

function createElement(tagName, textContent, className) {
  const element = document.createElement(tagName);
  if (textContent !== undefined) {
    element.textContent = textContent;
  }
  if (className) {
    element.className = className;
  }
  return element;
}

async function readCurrentPage() {
  elements.readPageButton.disabled = true;
  showStatus("Reading the listing...");
  try {
    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!activeTab || !/^https?:/.test(activeTab.url || "")) {
      throw new Error("Open a rental listing web page, then try again.");
    }
    const [injectionResult] = await chrome.scripting.executeScript({
      target: { tabId: activeTab.id },
      func: extractListing,
    });
    const listing = injectionResult && injectionResult.result;
    if (!listing) {
      throw new Error("Couldn't read this page. You can still paste the listing on the website.");
    }

    pageUrl = listing.url;
    elements.titleInput.value = listing.title || "";
    elements.descriptionInput.value = listing.description || "";
    elements.rentInput.value = listing.monthlyRent ?? "";
    elements.bedroomsInput.value = listing.bedrooms ?? "";
    elements.streetInput.value = listing.address.street || "";
    elements.cityInput.value = listing.address.city || "";
    elements.stateInput.value = listing.address.stateCode || "";
    elements.zipInput.value = listing.address.zipCode || "";
    elements.extractionNote.textContent =
      listing.method === "craigslist"
        ? "Read using Craigslist's page layout."
        : "Read from this page's general layout, so please double-check the fields.";

    elements.startSection.hidden = true;
    elements.reviewForm.hidden = false;
    showStatus("");
  } catch (readError) {
    showStatus(readError.message.includes("Cannot access") ? "This page can't be read by extensions." : readError.message);
  } finally {
    elements.readPageButton.disabled = false;
  }
}

function optionalValue(inputElement) {
  const trimmed = inputElement.value.trim();
  return trimmed === "" ? undefined : trimmed;
}

function buildSubmission() {
  const bedroomsText = optionalValue(elements.bedroomsInput);
  return {
    source: "extension",
    title: optionalValue(elements.titleInput),
    description: elements.descriptionInput.value.trim(),
    monthlyRent: optionalValue(elements.rentInput)?.replace(/[$,]/g, ""),
    bedrooms: bedroomsText === undefined ? undefined : Number(bedroomsText),
    address: {
      street: optionalValue(elements.streetInput),
      city: optionalValue(elements.cityInput),
      stateCode: optionalValue(elements.stateInput)?.toUpperCase(),
      zipCode: optionalValue(elements.zipInput),
    },
    contact: {},
    sourceUrl: pageUrl || undefined, // the API keeps only the website name, never the full link
  };
}

function renderResult(result) {
  const section = elements.resultSection;
  section.replaceChildren();

  const riskBox = createElement("div", undefined, `riskBox risk-${result.riskLevel}`);
  riskBox.append(createElement("strong", riskLabels[result.riskLevel] || result.riskLevel));
  riskBox.append(createElement("div", `${result.totalPoints} risk points`, "small"));
  section.append(riskBox);

  section.append(createElement("h2", "Red flags"));
  if (result.signals.length === 0) {
    section.append(createElement("p", "No red flags were found by the checks that ran.", "muted"));
  } else {
    const signalList = createElement("ul");
    for (const signal of result.signals) {
      const item = createElement("li");
      item.append(createElement("span", `${signal.severity} `, `severity risk-${signal.severity}`));
      item.append(document.createTextNode(signal.explanation));
      signalList.append(item);
    }
    section.append(signalList);
  }

  const skippedEntries = Object.entries(result.skipReasons || {});
  if (skippedEntries.length > 0) {
    section.append(createElement("h2", "Not checked"));
    const skippedList = createElement("ul", undefined, "small muted");
    for (const [checkName, reason] of skippedEntries) {
      skippedList.append(createElement("li", `${checkName}: ${reason}`));
    }
    section.append(skippedList);
  }

  section.append(createElement("h2", "Safety tips"));
  const tipList = createElement("ul", undefined, "small");
  for (const tip of result.safetyTips.slice(0, 4)) {
    tipList.append(createElement("li", tip));
  }
  section.append(tipList);
  section.append(createElement("p", result.disclaimer, "small muted"));
  section.hidden = false;
  section.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function analyzeListing(submitEvent) {
  submitEvent.preventDefault();
  elements.analyzeButton.disabled = true;
  elements.resultSection.hidden = true;
  showStatus("Analyzing...");

  const abortController = new AbortController();
  const timeoutId = setTimeout(() => abortController.abort(), requestTimeoutMs);
  try {
    const response = await fetch(`${apiBaseUrl}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildSubmission()),
      signal: abortController.signal,
    });
    if (response.status === 422) {
      const errorBody = await response.json().catch(() => ({}));
      const fieldMessages = (errorBody.detail || []).map(
        (error) => `${error.loc.filter((part) => part !== "body").join(".")}: ${error.msg.replace(/^Value error, /, "")}`,
      );
      throw new Error(`Please fix: ${fieldMessages.join("; ") || "some fields are invalid."}`);
    }
    if (response.status === 429) {
      throw new Error("Too many checks in a short time. Please wait a minute and try again.");
    }
    if (!response.ok) {
      throw new Error(`The analysis server had a problem (error ${response.status}). Please try again.`);
    }
    renderResult(await response.json());
    showStatus("");
  } catch (analyzeError) {
    showStatus(analyzeError.name === "AbortError"
      ? "The analysis took too long. Please try again."
      : analyzeError.message || "Could not reach the analysis server.");
  } finally {
    clearTimeout(timeoutId);
    elements.analyzeButton.disabled = false;
  }
}

elements.readPageButton.addEventListener("click", readCurrentPage);
elements.reviewForm.addEventListener("submit", analyzeListing);
