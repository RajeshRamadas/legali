import MainContent from "../ui/MainContent";
import "../ui/views/rera-rera.css";

export default function ReraLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <MainContent className="rr">{children}</MainContent>
      <aside className="hx-context-note">
        <div className="wrap">
          <div className="copyright">
            © 2026 Homexo Legal. Project details are compiled from Karnataka RERA (K-RERA) registrations and may lag the RERA portal; check the
            latest record at rera.karnataka.gov.in. Warning signs are worked out automatically from that record and are not a legal opinion on any
            project, developer or unit. Homexo Legal is not affiliated with K-RERA.
          </div>
        </div>
      </aside>
    </>
  );
}
