import type { Metadata } from "next";
import AdminShell from "./AdminShell";
import "../ui/views/admin-admin.css";
import "./cases.css";
import "./security.css";

export const metadata: Metadata = {
  title: "Homexo Legal · Staff workspace",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AdminShell>{children}</AdminShell>;
}
