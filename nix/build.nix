# Build derivations for Modelplane.
#
# All builders are functions that take an attrset of arguments and return a
# derivation. The actual build definitions live in flake.nix.
{ pkgs, crossplane-cli, ... }:
let
  # Map Nix system strings to the Go OS/arch pairs used in the crossplane-cli
  # release bundle.
  platformMap = {
    "x86_64-linux" = "linux_amd64";
    "aarch64-linux" = "linux_arm64";
    "x86_64-darwin" = "darwin_amd64";
    "aarch64-darwin" = "darwin_arm64";
  };

  # The docker-credential-up binary. The Crossplane CLI uses Docker's standard
  # credential chain for OCI registry auth. This helper provides credentials
  # for xpkg.upbound.io.
  dockerCredentialUpVersion = "0.44.3";
  dockerCredentialUpBins = {
    "x86_64-linux" = {
      url = "https://cli.upbound.io/stable/v${dockerCredentialUpVersion}/bin/linux_amd64/docker-credential-up";
      hash = "sha256-weGga6mxaNqoJx1X+mgtaOlxeXSRdHBSGUjX82V8S9A=";
    };
    "aarch64-linux" = {
      url = "https://cli.upbound.io/stable/v${dockerCredentialUpVersion}/bin/linux_arm64/docker-credential-up";
      hash = "sha256-3r3ZqIAKIAt/Ec9WSRbVt/rnut1k+Kx4mLNjPgTtzUc=";
    };
    "x86_64-darwin" = {
      # TODO(negz): Prefetch and verify this hash.
      url = "https://cli.upbound.io/stable/v${dockerCredentialUpVersion}/bin/darwin_amd64/docker-credential-up";
      hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
    };
    "aarch64-darwin" = {
      url = "https://cli.upbound.io/stable/v${dockerCredentialUpVersion}/bin/darwin_arm64/docker-credential-up";
      hash = "sha256-mSIOSuc/nKgo0hw66gpVrZlGR0l+7ZAu16YBb/4K/GE=";
    };
  };
in
{
  # The Crossplane CLI. The upstream flake produces a multi-platform release
  # bundle. We extract the binary for the current system.
  crossplane =
    { system }:
    let
      release = crossplane-cli.packages.${system}.default;
      platform = platformMap.${system};
    in
    pkgs.stdenvNoCC.mkDerivation {
      pname = "crossplane";
      version = release.version or "0.0.0";
      dontUnpack = true;
      installPhase = ''
        install -Dm755 ${release}/bin/${platform}/crossplane $out/bin/crossplane
      '';
    };

  # The docker-credential-up binary for xpkg.upbound.io authentication.
  dockerCredentialUp =
    { system }:
    let
      bin = dockerCredentialUpBins.${system};
    in
    pkgs.stdenvNoCC.mkDerivation {
      pname = "docker-credential-up";
      version = dockerCredentialUpVersion;
      src = pkgs.fetchurl {
        inherit (bin) url hash;
      };
      dontUnpack = true;
      installPhase = ''
        install -Dm755 $src $out/bin/docker-credential-up
      '';
    };
}
