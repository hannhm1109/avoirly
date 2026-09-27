import type { Metadata } from "next";
import { Shell } from "@/components/shell";
import "./globals.css";
import "./forms.css";

export const metadata: Metadata = {
  title: {
    default: "Avoirly · Vos dossiers fournisseurs",
    template: "%s · Avoirly",
  },
  description: "Spot invoice discrepancies. Simplify supplier claims.",
  robots: { index: false, follow: false },
};

export default function Layout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
