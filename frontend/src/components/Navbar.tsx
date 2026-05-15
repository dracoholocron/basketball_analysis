"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { logout } from "@/lib/api";

export default function Navbar() {
  const router = useRouter();

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
        <div className="flex items-center gap-4">
          <Link href="/games" className="text-sm text-gray-600 hover:text-gray-900 font-medium">
            Games
          </Link>
          <button
            onClick={handleLogout}
            className="btn-secondary text-sm py-1.5 px-3"
          >
            Sign out
          </button>
        </div>
      </div>
    </nav>
  );
}
