import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ITC — IT Operations and Systems Simulator",
  description: "Practice entry-level IT support skills by resolving simulated IT tickets.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      {/* suppressHydrationWarning: browser extensions (Grammarly, LastPass, etc.)
          inject data-* attributes onto <html>/<body> before React hydrates, which
          otherwise trips a hydration-mismatch warning that has nothing to do
          with app code. This only suppresses the *attribute* diff on these two
          elements -- it does not hide real hydration bugs in children. */}
      <body className="min-h-screen bg-void font-sans antialiased" suppressHydrationWarning>
        {/* Blocking (not `defer`/`type="module"`) and rendered before {children} so
            the theme attribute lands before first paint -- avoids a flash of the
            wrong theme on reload. Wrapped in try/catch since localStorage can throw
            in private-browsing modes; falls back to dark on any failure. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{if(localStorage.getItem("itc_theme")==="light"){document.documentElement.setAttribute("data-theme","light")}}catch(e){}`,
          }}
        />
        {children}
      </body>
    </html>
  );
}
