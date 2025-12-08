export default function TestTailwind() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-8">Teste de Classes Tailwind</h1>

      {/* Teste 1: Background básico */}
      <div className="mb-4">
        <h2 className="text-lg font-semibold mb-2">Teste 1: bg-red-500</h2>
        <div className="bg-red-500 p-4 text-white">
          Este div deveria ter fundo vermelho
        </div>
      </div>

      {/* Teste 2: Background com opacidade */}
      <div className="mb-4">
        <h2 className="text-lg font-semibold mb-2">Teste 2: bg-blue-500/50</h2>
        <div className="bg-blue-500/50 p-4">
          Este div deveria ter fundo azul semi-transparente
        </div>
      </div>

      {/* Teste 3: Backdrop blur */}
      <div className="mb-4 relative">
        <h2 className="text-lg font-semibold mb-2">Teste 3: backdrop-blur-sm (Tailwind)</h2>
        <div className="relative h-40 w-full overflow-hidden rounded-lg">
          {/* Fundo complexo para ver o blur */}
          <div className="absolute inset-0 bg-[url('https://placehold.co/600x400/orange/white?text=Background+Image')] bg-cover bg-center"></div>
          <div className="absolute inset-0 bg-gradient-to-r from-purple-500/80 to-pink-500/80"></div>
          <div className="absolute inset-0 flex items-center justify-center p-4">
             <div className="text-white font-bold text-2xl drop-shadow-md">Texto no Fundo</div>
          </div>

          {/* O Overlay com blur */}
          <div className="absolute inset-0 backdrop-blur-md bg-black/20 flex items-center justify-center z-10">
            <div className="bg-white/80 p-4 rounded shadow-lg backdrop-blur-none">
              <p className="font-bold text-black">Overlay com backdrop-blur-md</p>
            </div>
          </div>
        </div>
      </div>

      {/* Teste 4: Classe .loading-overlay do globals.css */}
      <div className="mb-4 relative">
        <h2 className="text-lg font-semibold mb-2">Teste 4: .loading-overlay (CSS Customizado)</h2>
        <div className="relative h-40 w-full rounded-lg overflow-hidden border border-gray-200">
          {/* Conteúdo "atrás" */}
          <div className="p-6 bg-white space-y-2">
            <h3 className="text-xl font-bold">Conteúdo do Card</h3>
            <p className="text-gray-600">Este é um texto de exemplo para verificar se o blur está funcionando corretamente sobre ele.</p>
            <div className="flex gap-2 mt-4">
              <div className="h-8 w-20 bg-blue-500 rounded"></div>
              <div className="h-8 w-20 bg-red-500 rounded"></div>
            </div>
          </div>
          
          {/* O Overlay aplicado via classe */}
          <div className="loading-overlay">
            {/* O loading-overlay agora tem um spinner via ::after, mas podemos por texto se quiser */}
          </div>
        </div>
      </div>

      {/* Teste 5: Style inline */}
      <div className="mb-4">
        <h2 className="text-lg font-semibold mb-2">Teste 5: Style inline (controle)</h2>
        <div style={{ backgroundColor: 'rgba(255, 0, 0, 0.5)' }} className="p-4 text-white">
          Este div usa style inline - deveria funcionar
        </div>
      </div>
    </div>
  );
}
