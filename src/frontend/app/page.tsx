import { DashboardClient } from "@/app/components/DashboardClient";
import { cookies } from "next/headers";
import { getUserInfoFromToken } from "@/app/utils/jwt-utils";

export default async function Home() {
  const cookieStore = await cookies();
  const idToken = cookieStore.get("id_token")?.value;
  const accessToken = cookieStore.get("access_token")?.value;

  const token = idToken || accessToken;
  const userInfo = token ? getUserInfoFromToken(token) : null;

  return <DashboardClient userName={userInfo?.name} />;
}