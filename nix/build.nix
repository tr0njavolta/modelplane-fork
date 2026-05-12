# Build derivations for Modelplane.
#
# All builders are functions that take an attrset of arguments and return a
# derivation. The actual build definitions live in flake.nix.
{ pkgs, ... }:
let
  # The up CLI isn't in nixpkgs. Fetch the binary from Upbound's CDN.
  upVersion = "0.44.3";
  upBins = {
    "x86_64-linux" = {
      url = "https://cli.upbound.io/stable/v${upVersion}/bin/linux_amd64/up";
      hash = "sha256-tvPmftejC2Pcsjn8kYf5DfPPUYHEtK5kQlQCJfyM7uc=";
    };
    "aarch64-linux" = {
      url = "https://cli.upbound.io/stable/v${upVersion}/bin/linux_arm64/up";
      hash = "sha256-gnJht2k343zPNr2qpoPQtTBgeVro4fyfJWs1idzaM1M=";
    };
    "x86_64-darwin" = {
      # TODO(negz): Prefetch and verify this hash.
      url = "https://cli.upbound.io/stable/v${upVersion}/bin/darwin_amd64/up";
      hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
    };
    "aarch64-darwin" = {
      url = "https://cli.upbound.io/stable/v${upVersion}/bin/darwin_arm64/up";
      hash = "sha256-Z2lbmnDxhgXDh+JN6yxIYtelQ2//Pg/HHHCgXQZBh/g=";
    };
  };

  # The Docker credential helper for xpkg.upbound.io. up shells out to it to
  # authenticate when fetching package dependencies.
  dockerCredentialUpBins = {
    "x86_64-linux" = {
      url = "https://cli.upbound.io/stable/v${upVersion}/bin/linux_amd64/docker-credential-up";
      hash = "sha256-weGga6mxaNqoJx1X+mgtaOlxeXSRdHBSGUjX82V8S9A=";
    };
    "aarch64-linux" = {
      url = "https://cli.upbound.io/stable/v${upVersion}/bin/linux_arm64/docker-credential-up";
      hash = "sha256-3r3ZqIAKIAt/Ec9WSRbVt/rnut1k+Kx4mLNjPgTtzUc=";
    };
    "x86_64-darwin" = {
      # TODO(negz): Prefetch and verify this hash.
      url = "https://cli.upbound.io/stable/v${upVersion}/bin/darwin_amd64/docker-credential-up";
      hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
    };
    "aarch64-darwin" = {
      url = "https://cli.upbound.io/stable/v${upVersion}/bin/darwin_arm64/docker-credential-up";
      hash = "sha256-mSIOSuc/nKgo0hw66gpVrZlGR0l+7ZAu16YBb/4K/GE=";
    };
  };
in
{
  # The Upbound up CLI.
  up =
    { system }:
    let
      bin = upBins.${system};
    in
    pkgs.stdenvNoCC.mkDerivation {
      pname = "up";
      version = upVersion;
      src = pkgs.fetchurl {
        inherit (bin) url hash;
      };
      dontUnpack = true;
      installPhase = ''
        install -Dm755 $src $out/bin/up
      '';
    };

  # The docker-credential-up binary. Required by up to authenticate with
  # xpkg.upbound.io when fetching package dependencies.
  dockerCredentialUp =
    { system }:
    let
      bin = dockerCredentialUpBins.${system};
    in
    pkgs.stdenvNoCC.mkDerivation {
      pname = "docker-credential-up";
      version = upVersion;
      src = pkgs.fetchurl {
        inherit (bin) url hash;
      };
      dontUnpack = true;
      installPhase = ''
        install -Dm755 $src $out/bin/docker-credential-up
      '';
    };

}
