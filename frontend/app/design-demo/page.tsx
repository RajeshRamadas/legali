import type { Metadata } from "next";
import DemoGallery from "./DemoGallery";

export const metadata: Metadata = {
  title: "Homexo UI · Design demo",
  description: "Interactive design review with fictional data. The production website is unchanged.",
  robots: { index: false, follow: false },
};

export default function DesignDemoPage() {
  return <DemoGallery />;
}
