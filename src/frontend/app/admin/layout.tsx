import { DashboardHeader } from "@/app/components/DashboardHeader";
import { cookies } from "next/headers";
import { getUserInfoFromToken } from "@/app/utils/jwt-utils";

export default async function AdminLayout({
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
    <div className="min-h-screen bg-background">
      <DashboardHeader userInfo={userInfo} />
      <main className="container mx-auto px-6 py-8">{children}</main>
    </div>
  );
}
