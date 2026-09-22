import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import { ThemeProvider } from "@/app/components/ThemeProvider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { QueryProvider } from "@/app/providers/QueryProvider";
import { ErrorBoundary } from "@/app/components/ErrorBoundary";
import { ServiceWorkerRegister } from "@/app/components/ServiceWorkerRegister";

// Retry de chunks JS que falharam ao carregar.
//
// Motivação: na volta do fluxo OAuth (gov.br → Keycloak → callback), o browser
// reutiliza uma conexão HTTP/2 que ficou idle durante o login e a camada de
// borda encerrou. Os chunks `/_next/static/chunks/*.js` recebem 503
// (text/plain) e o React nunca hidrata → loading infinito. Re-injetar o script
// após um delay força o browser a buscar em uma conexão nova.
//
// O listener é registrado no <head> ANTES dos script tags do Next.js, então
// qualquer falha é capturada em fase de captura no document.
const SCRIPT_RETRY_INLINE = `
(function () {
  if (typeof window === "undefined") return;
  var retried = {};
  document.addEventListener(
    "error",
    function (event) {
      var target = event.target;
      if (!target || target.tagName !== "SCRIPT") return;
      var src = target.src || "";
      if (src.indexOf("/_next/static/") === -1) return;
      // Segurança: só reinjeta scripts da mesma origem. URLs absolutas de
      // outros domínios que contenham "/_next/static/" no path NÃO passam.
      // O CSP (script-src 'self') já bloquearia a execução, mas o filtro
      // estrito evita qualquer tentativa de abuso na origem.
      var isAbsolute = src.indexOf("http://") === 0 || src.indexOf("https://") === 0;
      if (isAbsolute && src.indexOf(window.location.origin) !== 0) return;
      var attempts = retried[src] || 0;
      if (attempts >= 2) return;
      retried[src] = attempts + 1;
      var delay = attempts === 0 ? 2000 : 5000;
      setTimeout(function () {
        var script = document.createElement("script");
        script.src = src;
        script.async = true;
        document.head.appendChild(script);
      }, delay);
    },
    true,
  );
})();
`;

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "PIC Panel",
  description: "Dashboad acompanhamento PIC",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable} bg-background text-foreground`}>
        <Script
          id="chunk-retry"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{ __html: SCRIPT_RETRY_INLINE }}
        />
        <ErrorBoundary>
          <QueryProvider>
            <ThemeProvider
              attribute="class"
              defaultTheme="system"
              enableSystem
              disableTransitionOnChange
            >
              <TooltipProvider delayDuration={200}>
                  {children}
                  <Toaster />
              </TooltipProvider>
            </ThemeProvider>
          </QueryProvider>
        </ErrorBoundary>
        <ServiceWorkerRegister />
      </body>
    </html>
  );
}
