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
  // de hidratação. O cookie é apagado aqui via Set-Cookie para que o cliente
  // nunca o veja durante a hidratação do React (evita side effects em
  // useState initializers no DashboardClient).
  const isFreshLogin = freshLoginCookie === "1";

  // Apaga o cookie fresh_login no servidor. O DashboardClient recebe o valor
  // como prop booleana e faz a limpeza de cache no useLayoutEffect.
  if (isFreshLogin) {
    // Next.js App Router não expõe Set-Cookie direto num Server Component,
    // mas cookieStore.delete() adiciona o header Set-Cookie: fresh_login=; max-age=0
    // ao response do SSR de forma segura.
    cookieStore.delete("fresh_login");
  }

  return <DashboardClient userInfo={userInfo} isFreshLogin={isFreshLogin} />;
}