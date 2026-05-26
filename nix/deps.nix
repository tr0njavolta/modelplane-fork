# External dependencies not available in nixpkgs.
{ pkgs, crossplane-cli }:
let
  platformMap = {
    "x86_64-linux" = "linux_amd64";
    "aarch64-linux" = "linux_arm64";
    "x86_64-darwin" = "darwin_amd64";
    "aarch64-darwin" = "darwin_arm64";
  };
in
{
  # The Crossplane CLI. The upstream flake produces a multi-platform release
  # bundle; we extract the binary for the current system.
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
}
