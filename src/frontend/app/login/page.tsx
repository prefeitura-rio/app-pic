import { signIn } from "@/auth";
import { Button } from "@/app/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/app/components/ui/card";

export default function LoginPage() {
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
          <form
            action={async () => {
              "use server";
              await signIn("authentik", { redirectTo: "/" });
            }}
            className="w-full"
          >
            <Button className="w-full" type="submit">
              Sign In with Authentik
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
