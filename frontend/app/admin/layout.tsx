import type { Metadata } from "next";
import AdminShell from "./AdminShell";
import "../ui/views/admin-admin.css";

export const metadata: Metadata = {
  title: "Homexo Legal · Staff workspace",
  robots: { index: false, follow: false },
};

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <AdminShell>{children}</AdminShell>;
}
