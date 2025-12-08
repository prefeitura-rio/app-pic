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
import { Heart, Shield, Users, Building2, LogIn, AlertCircle } from "lucide-react";

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
    // kc_idp_hint: "govbr",
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
  const details = resolvedParams.details;

  async function handleLogin() {
    "use server";
    redirect(buildAuthUrl());
  }

  let errorMessage = null;
  if (error === "AccessDenied") {
    errorMessage = "Seu CPF não possui permissão de acesso ao sistema. Entre em contato com o administrador.";
    if (details) {
      errorMessage += ` (Detalhe: ${decodeURIComponent(details as string)})`;
    }
  } else if (error === "InactiveUser") {
    errorMessage = "Seu usuário está inativo. Entre em contato com o administrador para reativar seu acesso.";
  } else if (error) {
    errorMessage = "Ocorreu um erro durante a autenticação. Tente novamente.";
  }

  return (
    <div className="min-h-screen flex flex-col lg:flex-row">
      {/* Left Side - Branding & Info */}
      <div className="lg:w-1/2 bg-gradient-to-br from-primary via-primary to-primary-dark text-primary-foreground p-8 lg:p-12 flex flex-col justify-between relative overflow-hidden">
        {/* Decorative background elements */}
        <div className="absolute inset-0 opacity-10">
          <div className="absolute top-20 left-20 w-64 h-64 bg-white rounded-full blur-3xl"></div>
          <div className="absolute bottom-20 right-20 w-96 h-96 bg-white rounded-full blur-3xl"></div>
        </div>

        {/* Content */}
        <div className="relative z-10">
          {/* Logo & Title */}
          <div className="flex items-center gap-4 mb-8">
            <div className="bg-white/20 backdrop-blur-sm p-4 rounded-2xl">
              <Heart className="h-12 w-12" fill="currentColor" />
            </div>
            <div>
              <h1 className="text-3xl lg:text-4xl font-bold">Pequenos Cariocas</h1>
              <p className="text-primary-foreground/80 text-sm lg:text-base">
                Primeira Infância Integrada
              </p>
            </div>
          </div>

          {/* Description */}
          <div className="space-y-6 mt-12">
            <h2 className="text-2xl lg:text-3xl font-semibold leading-tight">
              Sistema Integrado de Gestão e Acompanhamento
            </h2>
            <p className="text-primary-foreground/90 text-lg">
              Plataforma unificada para acompanhamento de crianças e adolescentes atendidos
              pelos programas da Prefeitura do Rio de Janeiro.
            </p>
          </div>

          {/* Features */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-12">
            <div className="flex items-start gap-3">
              <div className="bg-white/20 backdrop-blur-sm p-2 rounded-lg">
                <Users className="h-5 w-5" />
              </div>
              <div>
                <h3 className="font-semibold">Gestão Integrada</h3>
                <p className="text-sm text-primary-foreground/80">
                  Saúde, Educação e Assistência Social
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="bg-white/20 backdrop-blur-sm p-2 rounded-lg">
                <Shield className="h-5 w-5" />
              </div>
              <div>
                <h3 className="font-semibold">Segurança LGPD</h3>
                <p className="text-sm text-primary-foreground/80">
                  Dados protegidos e auditados
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="bg-white/20 backdrop-blur-sm p-2 rounded-lg">
                <Building2 className="h-5 w-5" />
              </div>
              <div>
                <h3 className="font-semibold">Identidade Carioca</h3>
                <p className="text-sm text-primary-foreground/80">
                  Autenticação via GovBR
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="bg-white/20 backdrop-blur-sm p-2 rounded-lg">
                <Heart className="h-5 w-5" fill="currentColor" />
              </div>
              <div>
                <h3 className="font-semibold">Cuidado Integral</h3>
                <p className="text-sm text-primary-foreground/80">
                  Acompanhamento holístico
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="relative z-10 mt-8">
          <p className="text-sm text-primary-foreground/70">
            Desenvolvido por Prefeitura do Rio de Janeiro
          </p>
        </div>
      </div>

      {/* Right Side - Login Form */}
      <div className="lg:w-1/2 flex items-start justify-center p-8 pt-20 bg-background">
        <div className="w-full max-w-md">
          {/* Login Card */}
          <Card className="border-2 shadow-xl">
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
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
