import Link from "next/link";
import { Search } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#141414] mb-6"
        style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
      >
        <Search size={24} className="text-[#A1A1A1]" aria-hidden="true" />
      </div>

      <h1 className="text-6xl font-black text-[#EDEDED] mb-2">404</h1>
      <h2 className="text-lg font-semibold text-[#EDEDED] mb-2">Page not found</h2>
      <p className="text-sm text-[#A1A1A1] mb-8 max-w-xs">
        The page you are looking for does not exist or may have been moved.
      </p>

      <Link
        href="/"
        className="rounded-xl bg-violet-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-violet-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
      >
        Back to home
      </Link>
    </div>
  );
}