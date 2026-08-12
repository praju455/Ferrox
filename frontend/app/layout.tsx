import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ferrox | Industrial Product Intelligence",
  description:
    "Ferrox converts industrial product PDFs, supplier pages, and catalog dumps into traceable, validated product records.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
