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
    <div className="min-h-screen bg-background flex flex-col">
      <DashboardHeader userInfo={userInfo} />
      <main className="container mx-auto px-6 py-8 flex-1">{children}</main>
      <footer className="bg-muted mt-12 py-6 border-t">
        <div className="container mx-auto px-4 text-center text-sm text-muted-foreground">
          <p>Prefeitura do Rio de Janeiro • Programa Pequenos Cariocas</p>
          <p className="mt-1">Integração Saúde • Educação • Assistência Social</p>
        </div>
      </footer>
    </div>
  );
}
