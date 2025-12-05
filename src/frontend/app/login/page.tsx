import { redirect } from "next/navigation";
import { Button } from "@/app/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/app/components/ui/card";

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

export default function LoginPage() {
  async function handleLogin() {
    "use server";
    redirect(buildAuthUrl());
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background font-sans">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl font-semibold tracking-tight">
            Welcome Back
          </CardTitle>
          <CardDescription>
            Sign in to your account to continue
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form action={handleLogin}>
            <Button className="w-full" type="submit">
              Sign In with RMI
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
