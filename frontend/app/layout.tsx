import type { Metadata } from "next";
import "@fontsource-variable/plus-jakarta-sans";
import "./ui/tokens.css";
import "./ui/views/globals.css";
import "./ui/content-tones.css";
import "./ui/ui.css";
import SiteFrame from "./ui/SiteFrame";
import { AssistantProvider } from "./ui/useAssistant";

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
    <html lang="en" suppressHydrationWarning>
      <body>
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem('hx-theme');document.documentElement.dataset.theme=t==='light'||t==='dark'?t:matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'}catch(e){document.documentElement.dataset.theme='light'}`,
          }}
        />
        <AssistantProvider>
          <SiteFrame>{children}</SiteFrame>
        </AssistantProvider>
      </body>
    </html>
  );
}
