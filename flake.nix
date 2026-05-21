# New to Nix? Start here:
#   Language basics:  https://nix.dev/tutorials/nix-language
#   Flakes intro:     https://zero-to-nix.com/concepts/flakes
{
  description = "Modelplane - The open source control plane for AI models";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";

    # The Crossplane CLI, pinned to a specific commit.
    # https://github.com/crossplane/cli
    crossplane-cli.url = "github:crossplane/cli/bc595092600d24b56c506472d2731f4fa3cad333";
  };

  outputs =
    {
      self,
      nixpkgs,
      crossplane-cli,
    }:
    let
      supportedSystems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];

      # Helpers for per-system outputs.
      forAllSystems = f: nixpkgs.lib.genAttrs supportedSystems (system: forSystem system f);
      forSystem =
        system: f:
        f {
          inherit system;
          pkgs = import nixpkgs { inherit system; };
        };

    in
    {
      # CI checks (nix flake check).
      checks = forAllSystems (
        { pkgs, ... }:
        let
          checks = import ./nix/checks.nix { inherit pkgs self; };
        in
        {
          python = checks.python { };
          shell-lint = checks.shellLint { };
          nix-lint = checks.nixLint { };
        }
      );

      # Development commands (nix run .#<app>).
      apps = forAllSystems (
        { pkgs, system, ... }:
        let
          build = import ./nix/build.nix { inherit pkgs crossplane-cli; };
          apps = import ./nix/apps.nix { inherit pkgs; };
          crossplane = build.crossplane { inherit system; };
          dockerCredentialUp = build.dockerCredentialUp { inherit system; };
        in
        {
          build-crossplane = apps.buildCrossplane { inherit crossplane dockerCredentialUp; };
          test-crossplane = apps.testCrossplane { inherit crossplane dockerCredentialUp; };
          push-crossplane = apps.pushCrossplane { inherit crossplane dockerCredentialUp; };
          format = apps.format { };
          lint = apps.lint { };
        }
      );

      # Development shell (nix develop).
      devShells = forAllSystems (
        { pkgs, system, ... }:
        let
          build = import ./nix/build.nix { inherit pkgs crossplane-cli; };
          crossplane = build.crossplane { inherit system; };
          dockerCredentialUp = build.dockerCredentialUp { inherit system; };
        in
        {
          default = pkgs.mkShell {
            buildInputs = [
              # Crossplane
              crossplane
              dockerCredentialUp

              # Kubernetes
              pkgs.kubectl
              pkgs.kubernetes-helm
              pkgs.kind
              pkgs.docker-client

              # Python (for linting and testing composition functions)
              pkgs.python3
              pkgs.ruff
              pkgs.pyright

              # Nix
              pkgs.nixfmt-rfc-style
            ];

            shellHook = ''
              export PS1='\[\033[38;2;173;123;252m\][model\[\033[38;2;195;158;253m\]plane]\[\033[0m\] \w \$ '

              source <(kubectl completion bash 2>/dev/null)
              source <(helm completion bash 2>/dev/null)
              source <(kind completion bash 2>/dev/null)

              alias k=kubectl

              echo "Modelplane development shell"
              echo ""
              echo "  nix run .#build-crossplane    nix run .#format"
              echo "  nix run .#test-crossplane     nix run .#lint"
              echo "  nix run .#push-crossplane     nix flake check"
              echo ""
            '';
          };
        }
      );
    };
}
