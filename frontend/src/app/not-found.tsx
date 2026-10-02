import Link from "next/link";
import { Search } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-surface shadow-border mb-6">
        <Search size={20} className="text-text-muted" aria-hidden="true" />
      </div>

      <h1 className="text-5xl font-bold text-text-primary mb-2">404</h1>
      <h2 className="text-base font-medium text-text-primary mb-2">Page not found</h2>
      <p className="text-xs text-text-muted mb-8 max-w-xs leading-relaxed">
        The page you are looking for does not exist or may have been moved.
      </p>

      <Link
        href="/"
        className="rounded-lg bg-white px-5 py-2.5 text-xs font-semibold text-black tracking-wider uppercase transition-colors duration-150 hover:bg-neutral-200 focus-visible:ring-2 focus-visible:ring-blue-500"
      >
        Back to home
      </Link>
    </div>
  );
}