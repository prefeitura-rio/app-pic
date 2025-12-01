import { auth, signOut } from "@/auth";
import { Button } from "@/app/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/app/components/ui/card";

export default async function Home() {
  const session = await auth();

  return (
    <div className="flex min-h-screen items-center justify-center bg-background font-sans">
      <main className="flex min-h-screen w-full max-w-3xl flex-col items-center justify-between py-32 px-16 bg-background">
        <div className="flex flex-col items-center gap-6 text-center w-full">
          <h1 className="text-3xl font-semibold leading-10 tracking-tight text-foreground">
            app-pic Dashboard
          </h1>

          {session && (
            <div className="flex flex-col gap-4 w-full max-w-2xl">
              <Card>
                <CardHeader>
                  <CardTitle className="text-xl">Session Info</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground mb-2">
                    Logged in as: <strong className="text-foreground">{session.user?.email}</strong>
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-xl">Access Token</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="bg-muted p-4 rounded-md overflow-x-auto">
                    <code className="text-xs break-all text-foreground">
                      {session.accessToken || "No access token"}
                    </code>
                  </div>
                </CardContent>
              </Card>

              <form
                action={async () => {
                  "use server";
                  await signOut();
                }}
              >
                <Button variant="destructive" className="w-full" type="submit">
                  Sign Out
                </Button>
              </form>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
