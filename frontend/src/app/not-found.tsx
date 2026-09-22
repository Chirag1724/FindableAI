import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background text-white px-4">
      <h2 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-brandCyan to-brandPurple mb-4">
        404 — Page Not Found
      </h2>
      <p className="text-sm text-gray-400 mb-6">
        The requested resource could not be found.
      </p>
      <Link
        href="/"
        className="rounded-xl bg-gradient-to-r from-brandCyan to-brandIndigo px-5 py-2.5 text-sm font-semibold text-white shadow hover:opacity-90 transition"
      >
        Return Home
      </Link>
    </div>
  );
}
