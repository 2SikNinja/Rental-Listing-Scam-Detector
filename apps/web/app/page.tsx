import Link from "next/link";

import ListingForm from "@/components/ListingForm";

/**
 * Home page. A Server Component (the default in Next.js), so this header
 * is rendered on the server. Only ListingForm ships interactive
 * JavaScript to the browser.
 */
export default function Home() {
  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-12 sm:px-6">
      <header className="mb-10">
        <h1 className="text-3xl font-semibold tracking-tight">Rental Listing Scam Check</h1>
        <p className="mt-2 text-zinc-600 dark:text-zinc-400">
          Paste a rental listing to see which common scam warning signs it shows, and why. Results are a
          risk assessment, not a verdict.
        </p>
      </header>
      <ListingForm />
      <footer className="mt-16 border-t border-zinc-200 pt-6 text-sm text-zinc-500 dark:border-zinc-800">
        <Link className="underline" href="/privacy">Privacy policy</Link>
      </footer>
    </main>
  );
}
