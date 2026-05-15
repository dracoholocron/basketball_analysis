"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { logout } from "@/lib/api";
import { clsx } from "clsx";

const NAV_LINKS = [
  { href: "/games", label: "Games" },
  { href: "/jobs", label: "Jobs" },
  { href: "/admin", label: "Admin" },
];

export default function Navbar() {
  const router = useRouter();
  const pathname = usePathname();

  function handleLogout() {
    logout();
    router.replace("/login");
  }

  return (
    <nav className="sticky top-0 z-40 border-b border-gray-200 bg-white shadow-sm">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
        <Link href="/games" className="flex items-center gap-2 text-lg font-bold text-primary-700">
          🏀 <span>Basketball Analytics</span>
        </Link>
        <div className="flex items-center gap-1">
          {NAV_LINKS.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={clsx(
                "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                pathname.startsWith(href)
                  ? "bg-primary-50 text-primary-700"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
              )}
            >
              {label}
            </Link>
          ))}
          <button
            onClick={handleLogout}
            className="ml-3 btn-secondary text-sm py-1.5 px-3"
          >
            Sign out
          </button>
        </div>
      </div>
    </nav>
  );
}
