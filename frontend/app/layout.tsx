import type { Metadata } from "next";
import "@fontsource-variable/plus-jakarta-sans";
import "./ui/tokens.css";
import "./ui/views/globals.css";
import "./ui/content-tones.css";
import "./ui/ui.css";
import "./ui/premium.css";
import "./ui/accessibility.css";
import SiteFrame from "./ui/SiteFrame";
import { AssistantProvider } from "./ui/useAssistant";
import SkipLink from "./ui/SkipLink";

export const metadata: Metadata = {
  title:
    "Homexo Legal — Property Verification, Registration & Developer Operations",
  description:
    "Property legal verification, land acquisition due diligence, registration coordination and post-registration support for buyers and real estate developers in Bangalore.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-theme="dark">
      <body>
        <SkipLink />
        <AssistantProvider>
          <SiteFrame>{children}</SiteFrame>
        </AssistantProvider>
      </body>
    </html>
  );
}
