import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Homexo | Property services, made simpler",
  description: "Property services for homes, apartments, plots and land documentation.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
