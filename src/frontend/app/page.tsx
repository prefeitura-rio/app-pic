import { auth } from "@/auth";
import { DashboardClient } from "@/app/components/DashboardClient";
import { SessionProvider } from "next-auth/react";

export default async function Home() {
  const session = await auth();

  return (
    <SessionProvider session={session}>
      <DashboardClient />
    </SessionProvider>
  );
}