import { Heart } from "lucide-react";

export function DashboardHeader() {
  return (
    <header className="bg-primary text-primary-foreground shadow-lg">
      <div className="container mx-auto px-6 py-6">
        <div className="flex items-center gap-4">
          <div className="bg-primary-foreground/10 p-3 rounded-lg">
            <Heart className="h-8 w-8" fill="currentColor" />
          </div>
          <div>
            <h1 className="text-3xl font-bold">Pequenos Cariocas</h1>
            <p className="text-primary-foreground/80 text-sm">
              Primeira Infância Integrada • Prefeitura do Rio de Janeiro
            </p>
          </div>
        </div>
      </div>
    </header>
  );
}
