import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Homexo Legal — Property Verification, Registration & Developer Operations",
  description: "Property legal verification, land acquisition due diligence, registration coordination and post-registration support for buyers and real estate developers in Bangalore.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
