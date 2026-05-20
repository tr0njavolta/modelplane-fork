# CI check builders for Modelplane.
#
# Checks run inside the Nix sandbox without network or filesystem access. This
# makes them fully reproducible but means Go modules and npm dependencies must
# be prefetched.
#
# All checks are builder functions that take an attrset of arguments and return
# a derivation. The actual check definitions live in flake.nix.
{ pkgs, self }:
{
  # Run Python lint and formatting checks. Ruff works on source files only,
  # no network access needed. Configuration lives in pyproject.toml.
  python =
    _:
    pkgs.runCommand "modelplane-python-checks"
      {
        nativeBuildInputs = [ pkgs.ruff ];
      }
      ''
        # Copy source to a writable directory. Ruff needs to write a cache.
        cp -r ${self} src
        chmod -R u+w src
        cd src
        echo "Checking Python formatting..."
        ruff format --check functions/ lib/ tests/
        echo "Running Python linter..."
        ruff check functions/ lib/ tests/
        mkdir -p $out
        touch $out/.python-checks-passed
      '';

  # Run shell linters (shellcheck, shfmt).
  shellLint =
    _:
    pkgs.runCommand "modelplane-shell-lint"
      {
        nativeBuildInputs = [
          pkgs.findutils
          pkgs.shellcheck
          pkgs.shfmt
        ];
      }
      ''
        cd ${self}
        find . -name '*.sh' -type f | while read -r script; do
          shellcheck "$script"
          shfmt -d "$script"
        done
        mkdir -p $out
        touch $out/.shell-lint-passed
      '';

  # Run Nix linters (statix, deadnix, nixfmt).
  nixLint =
    _:
    pkgs.runCommand "modelplane-nix-lint"
      {
        nativeBuildInputs = [
          pkgs.statix
          pkgs.deadnix
          pkgs.nixfmt-rfc-style
        ];
      }
      ''
        statix check ${self}
        deadnix --fail ${self}/flake.nix ${self}/nix
        nixfmt --check ${self}/flake.nix ${self}/nix/*.nix
        mkdir -p $out
        touch $out/.nix-lint-passed
      '';
}
