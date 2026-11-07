/**
 * Reads the rental listing on the current page.
 *
 * Chrome copies this function's source into the page and runs it there
 * (chrome.scripting.executeScript), so it must be completely
 * self-contained: no imports and no references to anything outside it.
 *
 * Strategy, most reliable first:
 *   1. Site-specific selectors for Craigslist (stable, well-known markup)
 *   2. Structured data many sites embed for search engines (JSON-LD)
 *   3. Page metadata (Open Graph tags) and the largest block of text
 * The user reviews and can edit everything in the popup before sending.
 *
 * It only READS the page. It never clicks, submits, or changes anything.
 */
export function extractListing() {
  const maxDescriptionLength = 20000;

  function cleanText(value) {
    return (value || "").replace(/\s+/g, " ").trim();
  }

  function textOf(selector) {
    const element = document.querySelector(selector);
    return element ? cleanText(element.textContent) : "";
  }

  function metaContent(propertyName) {
    const element = document.querySelector(`meta[property="${propertyName}"], meta[name="${propertyName}"]`);
    return element ? cleanText(element.getAttribute("content")) : "";
  }

  function parseMoney(value) {
    const match = String(value || "").replace(/,/g, "").match(/\$?\s*(\d{3,6}(?:\.\d{1,2})?)/);
    return match ? Number(match[1]) : null;
  }

  function parseBedrooms(value) {
    const text = String(value || "").toLowerCase();
    if (/\bstudio\b/.test(text)) {
      return 0;
    }
    const match = text.match(/\b(\d{1,2})\s*(?:br|bd|bds|bed|beds|bedrooms?)\b/);
    return match ? Number(match[1]) : null;
  }

  function parseAddress(value) {
    // "123 Main St, Pasadena, CA 91101" -> parts. Anything not found is left empty.
    const text = cleanText(value);
    const zipMatch = text.match(/\b(\d{5})(?:-\d{4})?\b(?!.*\b\d{5}\b)/);
    const stateMatch = text.match(/\b([A-Z]{2})\b\s*\d{5}/);
    const streetMatch = text.match(/^\s*(\d{1,6}\s+[^,]{3,60})/);
    const cityMatch = text.match(/,\s*([A-Za-z .'-]{2,40}),\s*[A-Z]{2}\b/);
    return {
      street: streetMatch ? cleanText(streetMatch[1]) : "",
      city: cityMatch ? cleanText(cityMatch[1]) : "",
      stateCode: stateMatch ? stateMatch[1] : "",
      zipCode: zipMatch ? zipMatch[1] : "",
    };
  }

  function findJsonLdListing() {
    const scriptElements = document.querySelectorAll('script[type="application/ld+json"]');
    for (const scriptElement of scriptElements) {
      let parsedData;
      try {
        parsedData = JSON.parse(scriptElement.textContent);
      } catch {
        continue; // ignore malformed blocks
      }
      const candidates = Array.isArray(parsedData) ? parsedData : parsedData["@graph"] || [parsedData];
      for (const candidate of candidates) {
        if (!candidate || typeof candidate !== "object") {
          continue;
        }
        const offers = Array.isArray(candidate.offers) ? candidate.offers[0] : candidate.offers;
        const addressData = candidate.address || (candidate.itemOffered && candidate.itemOffered.address);
        if (offers || addressData || candidate.numberOfBedrooms || candidate.numberOfRooms) {
          return {
            title: cleanText(candidate.name),
            description: cleanText(candidate.description),
            monthlyRent: parseMoney(offers && (offers.price || (offers.priceSpecification && offers.priceSpecification.price))),
            bedrooms: Number.isFinite(Number(candidate.numberOfBedrooms ?? candidate.numberOfRooms))
              ? Number(candidate.numberOfBedrooms ?? candidate.numberOfRooms)
              : null,
            address: addressData && typeof addressData === "object"
              ? {
                  street: cleanText(addressData.streetAddress),
                  city: cleanText(addressData.addressLocality),
                  stateCode: cleanText(addressData.addressRegion).toUpperCase().slice(0, 2),
                  zipCode: cleanText(addressData.postalCode).slice(0, 5),
                }
              : null,
          };
        }
      }
    }
    return null;
  }

  function largestTextBlock() {
    let bestText = "";
    for (const element of document.querySelectorAll("article, main, section, div, p")) {
      // Only count text directly in this element's own paragraphs, not its whole subtree twice
      const blockText = cleanText(element.innerText || element.textContent);
      if (blockText.length > bestText.length && blockText.length < 30000 && element.children.length < 40) {
        bestText = blockText;
      }
    }
    return bestText;
  }

  const result = {
    site: location.hostname.replace(/^www\./, ""),
    url: location.href,
    title: "",
    description: "",
    monthlyRent: null,
    bedrooms: null,
    address: { street: "", city: "", stateCode: "", zipCode: "" },
    method: "generic",
  };

  // 1. Craigslist
  if (document.querySelector("#postingbody")) {
    const bodyElement = document.querySelector("#postingbody").cloneNode(true);
    bodyElement.querySelectorAll(".print-information, .print-qrcode-container").forEach((node) => node.remove());
    const housingText = textOf(".housing");
    result.title = textOf("#titletextonly");
    result.description = cleanText(bodyElement.textContent);
    result.monthlyRent = parseMoney(textOf(".postingtitletext .price") || textOf(".price"));
    result.bedrooms = parseBedrooms(housingText);
    const mapAddress = textOf(".mapaddress");
    if (mapAddress) {
      result.address = { ...result.address, ...Object.fromEntries(
        Object.entries(parseAddress(mapAddress)).filter(([, value]) => value)
      ) };
      if (!result.address.street && /^\d/.test(mapAddress)) {
        result.address.street = mapAddress;
      }
    }
    result.method = "craigslist";
  } else {
    // 2. Structured data
    const jsonLdListing = findJsonLdListing();
    if (jsonLdListing) {
      result.title = jsonLdListing.title;
      result.description = jsonLdListing.description;
      result.monthlyRent = jsonLdListing.monthlyRent;
      result.bedrooms = jsonLdListing.bedrooms;
      if (jsonLdListing.address) {
        result.address = jsonLdListing.address;
      }
      result.method = "structured-data";
    }

    // 3. Fill any gaps from metadata and visible text
    result.title = result.title || metaContent("og:title") || cleanText(document.title);
    const visibleText = largestTextBlock();
    if (!result.description || result.description.length < 80) {
      result.description = visibleText.length > (result.description || "").length
        ? visibleText
        : result.description || metaContent("og:description") || metaContent("description");
    }
    const searchableText = `${result.title} ${result.description}`;
    result.monthlyRent = result.monthlyRent ?? parseMoney((searchableText.match(/\$\s?\d[\d,]{2,6}(?:\s*\/\s*(?:mo|month))?/i) || [""])[0]);
    result.bedrooms = result.bedrooms ?? parseBedrooms(searchableText);
    if (!result.address.zipCode) {
      const foundAddress = parseAddress((searchableText.match(/\d{1,6}\s+[^,\n]{3,60},\s*[A-Za-z .'-]{2,40},\s*[A-Z]{2}\s*\d{5}/) || [""])[0]);
      result.address = { ...result.address, ...Object.fromEntries(Object.entries(foundAddress).filter(([, value]) => value)) };
    }
  }

  result.description = result.description.slice(0, maxDescriptionLength);
  return result;
}
