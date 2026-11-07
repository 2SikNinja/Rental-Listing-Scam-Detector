/**
 * Tests for extractListing.js, run against saved sample pages in a
 * simulated browser (jsdom). Run with: npm test
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { JSDOM } from "jsdom";

import { extractListing } from "../extractListing.js";

/** Load a fixture page as if it were open in the browser, then run the extractor on it. */
function extractFrom(fixtureName, pageUrl = "https://www.example.org/listing/123") {
  const html = readFileSync(new URL(`./fixtures/${fixtureName}`, import.meta.url), "utf8");
  const pageDom = new JSDOM(html, { url: pageUrl });
  globalThis.document = pageDom.window.document;
  globalThis.location = pageDom.window.location;
  try {
    return extractListing();
  } finally {
    delete globalThis.document;
    delete globalThis.location;
  }
}

test("reads a Craigslist post using its page layout", () => {
  const listing = extractFrom("craigslistListing.html", "https://losangeles.craigslist.org/apa/d/example/123.html");
  assert.equal(listing.method, "craigslist");
  assert.equal(listing.site, "losangeles.craigslist.org");
  assert.equal(listing.title, "Sunny 2br near the park, laundry in unit");
  assert.equal(listing.monthlyRent, 1450);
  assert.equal(listing.bedrooms, 2);
  assert.equal(listing.address.street, "412 Example Ave");
  assert.match(listing.description, /keys will be mailed/);
});

test("removes Craigslist's QR code text from the description", () => {
  const listing = extractFrom("craigslistListing.html");
  assert.doesNotMatch(listing.description, /QR Code/);
});

test("reads structured data and skips malformed blocks", () => {
  const listing = extractFrom("structuredDataListing.html");
  assert.equal(listing.method, "structured-data");
  assert.equal(listing.title, "1 Bedroom Apartment with Balcony");
  assert.equal(listing.monthlyRent, 1750);
  assert.equal(listing.bedrooms, 1);
  assert.deepEqual(listing.address, {
    street: "200 Sample St Unit 4",
    city: "Austin",
    stateCode: "TX",       // uppercased
    zipCode: "78704",      // ZIP+4 trimmed to 5 digits
  });
});

test("falls back to visible text on a plain page", () => {
  const listing = extractFrom("genericListing.html");
  assert.equal(listing.method, "generic");
  assert.equal(listing.title, "3 bed house for rent - $1,200/month");
  assert.equal(listing.monthlyRent, 1200);
  assert.equal(listing.bedrooms, 3);
  assert.equal(listing.address.zipCode, "67203");
  assert.equal(listing.address.stateCode, "KS");
  assert.match(listing.description, /Cash App/);
  assert.doesNotMatch(listing.description, /Copyright/); // picks the post, not the whole page
});

test("never returns more description than the API accepts", () => {
  const longPage = `<html><body><div><p>${"Spacious apartment. ".repeat(3000)}</p></div></body></html>`;
  const pageDom = new JSDOM(longPage, { url: "https://example.org/" });
  globalThis.document = pageDom.window.document;
  globalThis.location = pageDom.window.location;
  try {
    assert.ok(extractListing().description.length <= 20000);
  } finally {
    delete globalThis.document;
    delete globalThis.location;
  }
});

test("is self-contained, so Chrome can inject it into a page", () => {
  // executeScript serializes the function's source. Any reference to a
  // module-level name would be undefined inside the page.
  const source = extractListing.toString();
  assert.doesNotMatch(source, /\bimport\b|\brequire\(/);
});
