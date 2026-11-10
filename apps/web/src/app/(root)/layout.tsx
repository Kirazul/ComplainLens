import "../globals.css";

export const metadata = { title: "LunaGo" };

// Minimal root layout for "/", which only forwards visitors to their language.
export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body className="bg-night">{children}</body>
    </html>
  );
}
