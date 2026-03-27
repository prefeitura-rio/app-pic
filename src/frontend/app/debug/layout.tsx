import { DashboardHeader } from "@/app/components/DashboardHeader";
import { Footer } from "@/app/components/Footer";
import { cookies } from "next/headers";
import { getUserInfoFromToken } from "@/app/utils/jwt-utils";

export default async function DebugLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const cookieStore = await cookies();
  const idToken = cookieStore.get("id_token")?.value;
  const accessToken = cookieStore.get("access_token")?.value;

  const token = idToken || accessToken;
  const userInfo = token ? getUserInfoFromToken(token) : null;

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <DashboardHeader userInfo={userInfo} />
      <main className="flex-1">{children}</main>
      <Footer />
    </div>
  );
}
