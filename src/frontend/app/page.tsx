import { auth, signIn, signOut } from "@/auth";

export default async function Home() {
  const session = await auth();

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex min-h-screen w-full max-w-3xl flex-col items-center justify-between py-32 px-16 bg-white dark:bg-black">
        <div className="flex flex-col items-center gap-6 text-center w-full">
          <h1 className="text-3xl font-semibold leading-10 tracking-tight text-black dark:text-zinc-50">
            app-pic Authentication Test
          </h1>

          {session ? (
            <div className="flex flex-col gap-4 w-full max-w-2xl">
              <div className="p-6 border border-zinc-200 dark:border-zinc-800 rounded-lg">
                <h2 className="text-xl font-medium mb-4">Session Info</h2>
                <p className="text-sm text-zinc-600 dark:text-zinc-400 mb-2">
                  Logged in as: <strong>{session.user?.email}</strong>
                </p>
              </div>

              <div className="p-6 border border-zinc-200 dark:border-zinc-800 rounded-lg">
                <h2 className="text-xl font-medium mb-4">Access Token</h2>
                <div className="bg-zinc-100 dark:bg-zinc-900 p-4 rounded overflow-x-auto">
                  <code className="text-xs break-all">
                    {session.accessToken || "No access token"}
                  </code>
                </div>
              </div>

              <form
                action={async () => {
                  "use server";
                  await signOut();
                }}
              >
                <button
                  type="submit"
                  className="w-full flex h-12 items-center justify-center rounded-full bg-red-600 px-5 text-white transition-colors hover:bg-red-700"
                >
                  Sign Out
                </button>
              </form>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              <p className="text-lg text-zinc-600 dark:text-zinc-400">
                You are not logged in
              </p>
              <form
                action={async () => {
                  "use server";
                  await signIn("authentik");
                }}
              >
                <button
                  type="submit"
                  className="flex h-12 items-center justify-center gap-2 rounded-full bg-blue-600 px-8 text-white transition-colors hover:bg-blue-700"
                >
                  Sign In with Authentik
                </button>
              </form>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
