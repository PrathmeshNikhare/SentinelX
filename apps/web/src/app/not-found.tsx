import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <div className="text-center">
        <h1 className="text-base font-semibold">Page not found</h1>
        <Link href="/" className="mt-2 inline-block underline">
          Back to overview
        </Link>
      </div>
    </main>
  );
}
