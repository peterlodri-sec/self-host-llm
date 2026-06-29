{
  description = "Ultrawhale Dogfeed Pipeline — industrial-grade Q&A data synthesis";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
  };

  outputs = inputs@{ flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" "x86_64-darwin" ];

      perSystem = { pkgs, ... }: {
        packages.default = pkgs.python3Packages.buildPythonPackage {
          pname = "ultrawhale";
          version = "2.0.0";
          format = "pyproject";

          src = ./.;

          nativeBuildInputs = with pkgs.python3Packages; [
            hatchling
          ];

          propagatedBuildInputs = with pkgs.python3Packages; [
            openai
            huggingface-hub
            psutil
            requests
          ];

          nativeCheckInputs = with pkgs.python3Packages; [
            pytest
            pytest-cov
            pytest-mock
            ruff
            mypy
          ];

          checkPhase = ''
            pytest tests/ -m "not requires_hf_token" --no-cov
          '';

          meta = with pkgs.lib; {
            description = "High-throughput Q&A generation pipeline for training LLMs";
            homepage = "https://github.com/peterlodri-sec/ultrawhale-dogfood-pipeline";
            license = licenses.mit;
            platforms = platforms.unix;
            maintainers = [];
          };
        };

        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            python312
            uv
          ] ++ (with pkgs.python3Packages; [
            openai
            huggingface-hub
            psutil
            requests
            pytest
            pytest-cov
            pytest-mock
            ruff
            mypy
          ]);

          shellHook = ''
            echo "🐋 Ultrawhale dev shell"
            echo "  uv sync --all-extras  # install dev deps"
            echo "  uv run pytest          # run tests"
          '';
        };
      };
    };
}
