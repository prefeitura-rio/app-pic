import { redirect } from "next/navigation";
import { Button } from "@/app/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/app/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Users, Building2, LogIn, AlertCircle, Heart, GraduationCap, Stethoscope, Home } from "lucide-react";
import { DashboardHeader } from "@/app/components/DashboardHeader";
import { Footer } from "@/app/components/Footer";
import { LoginFormWithFallback } from "@/app/components/LoginFormWithFallback";

/**
 * Build Keycloak OAuth2 authorization URL (server-side)
 */
function buildAuthUrl(): string {
  const baseUrl = `${process.env.RMI_ISSUER}/protocol/openid-connect/auth`;
  const params = new URLSearchParams({
    client_id: process.env.RMI_CLIENT_ID!,
    redirect_uri: `${process.env.NEXTAUTH_URL}/api/auth/callback/rmi`,
    response_type: "code",
    scope: "openid profile email",
    // Skip Identidade Carioca selection page and go directly to GovBR login
    kc_idp_hint: "govbr",
    // Force re-authentication even if SSO session exists
    // This ensures users must enter credentials after logout
    prompt: "login",
  });

  return `${baseUrl}?${params.toString()}`;
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const resolvedParams = await searchParams;
  const error = resolvedParams.error;
  const authUrl = buildAuthUrl();

  async function handleLogin() {
    "use server";
    redirect(authUrl);
  }

  let errorMessage = null;
  if (error === "AccessDenied") {
    errorMessage = "Seu CPF não possui permissão de acesso ao sistema. Entre em contato com o administrador.";
  } else if (error === "InactiveUser") {
    errorMessage = "Seu usuário está inativo. Entre em contato com o administrador para reativar seu acesso.";
  } else if (error) {
    errorMessage = "Ocorreu um erro durante a autenticação. Tente novamente.";
  }

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <DashboardHeader showUserControls={false} />

      {/* Main Content - Split Layout */}
      <main className="flex-1 container mx-auto px-6 py-12">
        <div className="grid lg:grid-cols-2 gap-12 items-center max-w-6xl mx-auto">

          {/* Left Side - Project Description */}
          <div className="space-y-8">
            <div className="space-y-4">
              <p className="text-lg text-foreground leading-relaxed">
                Plataforma integrada para acompanhamento de crianças e gestantes,
                reunindo informações de saúde, educação e assistência social.
              </p>
              <p className="text-foreground/80">
                Visualize indicadores, monitore o cumprimento de protocolos e
                garanta o cuidado integral às famílias beneficiárias.
              </p>
            </div>

            {/* Features Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-4">
              <div className="flex items-start gap-3 p-4 rounded-lg bg-muted/50">
                <div className="bg-primary/10 p-2 rounded-lg shrink-0">
                  <Stethoscope className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <h3 className="font-semibold text-sm">Saude</h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    Vacinacao, consultas e acompanhamento
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3 p-4 rounded-lg bg-muted/50">
                <div className="bg-primary/10 p-2 rounded-lg shrink-0">
                  <GraduationCap className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <h3 className="font-semibold text-sm">Educacao</h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    Matricula, frequencia e desempenho
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3 p-4 rounded-lg bg-muted/50">
                <div className="bg-primary/10 p-2 rounded-lg shrink-0">
                  <Home className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <h3 className="font-semibold text-sm">Assistencia</h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    CRAS, cadastro e beneficios
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Right Side - Login Card */}
          <div className="flex justify-center lg:justify-end">
            <Card className="border-2 shadow-xl w-full max-w-md">
              <CardHeader className="text-center pb-8 pt-10">
                <div className="mx-auto w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center mb-4">
                  <LogIn className="h-8 w-8 text-primary" />
                </div>
                <CardTitle className="text-3xl font-bold">
                  Bem-vindo
                </CardTitle>
                <CardDescription className="text-base mt-2">
                  Acesse o sistema com sua conta gov.br
                </CardDescription>
              </CardHeader>

              <CardContent className="px-8 pb-10 space-y-6">
                {errorMessage && (
                  <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>Acesso Negado</AlertTitle>
                    <AlertDescription>
                      {errorMessage}
                    </AlertDescription>
                  </Alert>
                )}

                 <LoginFormWithFallback authUrl={authUrl}>
                   <form action={handleLogin}>
                     <Button
                       className="w-full h-12 text-base font-semibold gap-2 shadow-lg hover:shadow-xl transition-all"
                       type="submit"
                       size="lg"
                     >
                       <LogIn className="h-5 w-5" />
                       Entrar com gov.br
                     </Button>
                   </form>
                 </LoginFormWithFallback>
              </CardContent>
            </Card>
          </div>

        </div>
      </main>

      <Footer />
    </div>
  );
}
