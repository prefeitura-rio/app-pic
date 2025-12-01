{
  description = "app-pic - Monorepo Development Environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          config.allowUnfree = true;
        };
      in
      {
        devShells.default = pkgs.mkShell {
          name = "app-pic-dev";

          buildInputs = with pkgs; [
            # Python for backend (FastAPI)
            python313
            uv

            # Node.js for frontend
            nodejs_22

            # Utilities
            curl
            jq
            just

            # Git
            git
          ];

          shellHook = ''
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

            # Load .env files if they exist
            if [ -f .env ]; then
              echo "Loading .env file..."
              set -a
              source .env
              set +a
            fi

            if [ -f .env.local ]; then
              echo "Loading .env.local file..."
              set -a
              source .env.local
              set +a
            fi
          '';
        };
      }
    );
}
