import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CodeExplorer - Repository Analysis Dashboard",
  description: "Analyze GitHub repositories and visualize code structure, dependencies, and key insights",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        {children}
      </body>
    </html>
  );
}
