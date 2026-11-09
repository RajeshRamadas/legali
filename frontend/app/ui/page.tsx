import type { Metadata } from "next";
import Showcase from "./Showcase";
import MainContent from "./MainContent";
export const metadata: Metadata = {
  title: "Homexo UI component review",
  robots: { index: false, follow: false },
};
export default function UIPage() {
  return <MainContent><Showcase /></MainContent>;
}
