# Chrome Extension

Checks the rental listing you are viewing, using the same analysis API as the website.

**How it works:** click the toolbar icon, then **Read this listing**. The extension reads the current page (title, description, price, bedrooms, address), shows you what it found so you can fix anything, and only sends it when you click **Analyze listing**.

## Try it locally

1. Open `chrome://extensions` in Chrome
2. Turn on **Developer mode** (top right)
3. Click **Load unpacked** and choose this `extension` folder
4. Open a rental listing, click the extension's icon (pin it from the puzzle piece menu), then **Read this listing**

After editing files, click the reload icon on the extension's card in `chrome://extensions`.

## How it reads pages

[`extractListing.js`](extractListing.js) tries, in order:

1. **Craigslist's page layout** (stable, well-known element IDs)
2. **Structured data** that many listing sites embed for search engines (schema.org JSON-LD)
3. **Page metadata and the largest block of visible text**, as a fallback for sites like Facebook Marketplace

Sites change their markup, so extraction is best effort. That's why the user always reviews the fields before sending.

## Security and privacy design

| Decision | Why |
|---|---|
| `activeTab` instead of access to all sites | The extension can read a page only after you click, and only that tab. No background access to your browsing |
| One host permission: the analysis API | It cannot send data anywhere else |
| No content scripts and no background service worker | Nothing runs on pages unless you ask |
| Review step before sending | You see and control exactly what leaves your browser |
| Results rendered with `textContent`, never `innerHTML` | A malicious listing page can't inject HTML or scripts into the extension |
| Strict content security policy | Only the extension's own scripts can run in its pages |
| Only the website name of the listing link is stored | The API discards the full URL |

## Tests

```bash
npm install
npm test
```

The tests load saved sample pages (Craigslist-style, structured data, plain page) in a simulated browser and check what is extracted.

## Publishing to the Chrome Web Store

CI builds `rental-scam-check-extension.zip` (runtime files only) as a downloadable artifact on every push. To publish:

1. Register at the [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole) (one-time $5 fee)
2. Upload the zip from the latest CI run
3. Fill in the store listing and privacy tab using the text below
4. Submit for review

**Single purpose:**
> Checks the rental listing the user is viewing for common scam warning signs and explains each one.

**Permission justifications:**
- `activeTab`: Reads the listing on the current tab only after the user clicks "Read this listing."
- `scripting`: Runs the one function that reads the listing's text from that tab.
- Host permission (the analysis API): Sends the listing the user chose to check to the analysis server.

**Data usage disclosures:** The extension sends the listing's text, price, address, and any contact details in the listing to the analysis server, only when the user clicks Analyze. No browsing history, personal information about the user, or data from other pages is collected. Data is not sold or used for anything other than the analysis.

**Privacy policy URL:** `https://rental-scam-detector-virid.vercel.app/privacy`

## Limitations

- Photos aren't sent from the extension yet (that would need permission to read image hosts). Use the website to check photos.
- Facebook Marketplace pages are heavily scripted, so the fallback reader may miss the price or address. The review step lets you fill them in.
