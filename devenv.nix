{ pkgs, ... }:

{
  languages.python = {
    enable = true;
    version = "3.13";
    uv = {
      enable = true;
      sync.enable = true;
    };
  };

  languages.javascript = {
    enable = true;
    package = pkgs.nodejs_22;
    npm.enable = true;
  };

  packages = with pkgs; [
    curl
    jq
    just
  ];

  enterShell = ''
    echo "🏛️  app-pic Development Environment"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Node.js: $(node --version)"
    echo "npm: $(npm --version)"
    echo "Python: $(python --version)"
    echo "uv: $(uv --version)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "🐍 Backend (FastAPI):"
    echo "  📦 Install dependencies: uv sync"
    echo "  🚀 Start dev server: uv run uvicorn src.main:app --reload"
    echo ""
    echo "⚛️  Frontend (Next.js):"
    echo "  📦 Install dependencies: cd src/frontend && npm install"
    echo "  🚀 Start dev server: cd src/frontend && npm run dev"
    echo "  🏗️  Build: cd src/frontend && npm run build"
    echo ""
  '';
}
