import { DashboardClient } from "@/app/components/DashboardClient";
import { cookies } from "next/headers";
import { getUserInfoFromToken } from "@/app/utils/jwt-utils";

export default async function Home() {
  const cookieStore = await cookies();
  const idToken = cookieStore.get("id_token")?.value;
  const accessToken = cookieStore.get("access_token")?.value;
  const freshLoginCookie = cookieStore.get("fresh_login")?.value;

  const token = idToken || accessToken;
  const userInfo = token ? getUserInfoFromToken(token) : null;

  // Detecta fresh login no servidor — leitura determinística, sem race condition
  // de hidratação. O cookie fresh_login tem maxAge: 60 e expira naturalmente;
  // não tentamos deletá-lo aqui porque cookieStore.delete() não é permitido
  // em Server Components (apenas em Server Actions e Route Handlers).
  // O DashboardClient recebe o valor como prop booleana e executa a limpeza
  // de cache no useLayoutEffect após o mount.
  const isFreshLogin = freshLoginCookie === "1";

  return <DashboardClient userInfo={userInfo} isFreshLogin={isFreshLogin} />;
}