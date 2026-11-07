import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy Policy | Rental Listing Scam Check",
  description: "What the Rental Listing Scam Check website and Chrome extension collect, how it is stored, and for how long.",
};

const effectiveDate = "November 7, 2026";

/**
 * Privacy policy for the website and the Chrome extension. The Chrome Web
 * Store requires a published policy for any extension that sends page data
 * anywhere. Keep this in sync with what the code actually does.
 */
export default function PrivacyPage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-12 sm:px-6">
      <article className="flex flex-col gap-6 leading-7">
        <header>
          <h1 className="text-3xl font-semibold tracking-tight">Privacy Policy</h1>
          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">Effective {effectiveDate}</p>
        </header>

        <p>
          Rental Listing Scam Check (the website and the Chrome extension) checks rental listings for common scam
          warning signs. It has one purpose, and it only collects what that purpose needs. There are no accounts, no
          ads, no analytics or tracking scripts, and no data is sold or shared for marketing.
        </p>

        <section>
          <h2 className="text-xl font-semibold">What is collected</h2>
          <p className="mt-2">Only the listing you choose to check, and only when you submit it:</p>
          <ul className="mt-2 list-disc pl-6">
            <li>Listing title, description, rent, bedrooms, bathrooms, and address</li>
            <li>Contact details that appear in the listing (the landlord&apos;s email or phone number)</li>
            <li>Photos you upload on the website</li>
            <li>The website name of a listing link (for example, craigslist.org), never the full link</li>
          </ul>
          <p className="mt-2">
            Your IP address is used briefly in memory to limit how many checks one visitor can run per minute. It is
            not stored.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold">The Chrome extension</h2>
          <ul className="mt-2 list-disc pl-6">
            <li>It reads a page only when you click &quot;Read this listing,&quot; and only the tab you are viewing.</li>
            <li>It shows you what it found, and nothing is sent until you click &quot;Analyze listing.&quot;</li>
            <li>It does not read your browsing history, other tabs, or any page you don&apos;t ask it to check.</li>
            <li>It sends data only to this service&apos;s analysis server.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold">How it is stored</h2>
          <ul className="mt-2 list-disc pl-6">
            <li>
              Emails and phone numbers are removed from the stored text and kept only as one-way keyed hashes. These
              can show that the same number appeared on another listing, but the number itself cannot be read back.
            </li>
            <li>
              Photos are never stored. Each photo is reduced to a short fingerprint used to spot copied photos, and
              the image is discarded.
            </li>
            <li>Listings and results are deleted automatically after 180 days.</li>
            <li>Data is stored in the United States and encrypted in transit.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold">Service providers</h2>
          <ul className="mt-2 list-disc pl-6">
            <li>Google Cloud (runs the analysis server) and Vercel (hosts this website)</li>
            <li>Supabase (stores results, as described above)</li>
            <li>
              The U.S. Census Bureau geocoder receives a submitted street address to confirm it exists. Nothing else
              is sent to it.
            </li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold">Results are not verdicts</h2>
          <p className="mt-2">
            Each result is an automated risk assessment based on common scam patterns. It is not a finding that any
            landlord or listing is fraudulent.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold">Questions or deletion requests</h2>
          <p className="mt-2">
            Open an issue on the project&apos;s{" "}
            <a className="underline" href="https://github.com/2SikNinja/Rental-Listing-Scam-Detector/issues">
              GitHub page
            </a>
            . Changes to this policy will be posted here with a new effective date.
          </p>
        </section>

        <p>
          <Link className="underline" href="/">
            Back to the scam check
          </Link>
        </p>
      </article>
    </main>
  );
}
