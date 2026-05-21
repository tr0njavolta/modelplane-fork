# Interactive development commands for Modelplane.
#
# Apps run outside the Nix sandbox with full filesystem and network access.
# They're designed for local development.
#
# All apps are builder functions that take an attrset of arguments and return a
# complete app definition ({ type, meta.description, program }). Most use
# writeShellApplication to create the program. The text block is preprocessed:
#
#   ${somePkg}/bin/foo   -> /nix/store/.../bin/foo  (Nix store path)
#   ''${SOME_VAR}        -> ${SOME_VAR}             (shell variable, escaped)
#
# Each app declares its tool dependencies via runtimeInputs, with inheritPath
# set to false. This ensures apps only use explicitly declared tools.
{ pkgs }:
{
  # Format Python code.
  format = _: {
    type = "app";
    meta.description = "Format Python code";
    program = pkgs.lib.getExe (
      pkgs.writeShellApplication {
        name = "modelplane-format";
        runtimeInputs = [ pkgs.ruff ];
        inheritPath = false;
        text = ''
          ruff format functions/
          ruff check --fix functions/
        '';
      }
    );
  };

  # Lint Python code.
  lint = _: {
    type = "app";
    meta.description = "Lint Python code";
    program = pkgs.lib.getExe (
      pkgs.writeShellApplication {
        name = "modelplane-lint";
        runtimeInputs = [ pkgs.ruff ];
        inheritPath = false;
        text = ''
          ruff format --check functions/
          ruff check functions/
        '';
      }
    );
  };

  # Build the Crossplane project (XRDs, functions, and compositions).
  buildCrossplane =
    { crossplane, dockerCredentialUp }:
    {
      type = "app";
      meta.description = "Build the Crossplane project";
      program = pkgs.lib.getExe (
        pkgs.writeShellApplication {
          name = "modelplane-build-crossplane";
          runtimeInputs = [
            crossplane
            dockerCredentialUp
          ];
          inheritPath = false;
          text = ''
            crossplane project build "$@"
          '';
        }
      );
    };

  # Run unit tests. Builds the project first to generate Pydantic models,
  # then creates a venv with function dependencies and runs unittest
  # across all functions.
  testCrossplane =
    { crossplane, dockerCredentialUp }:
    {
      type = "app";
      meta.description = "Build the Crossplane project and run unit tests";
      program = pkgs.lib.getExe (
        pkgs.writeShellApplication {
          name = "modelplane-test-crossplane";
          runtimeInputs = [
            crossplane
            dockerCredentialUp
            pkgs.python3
          ];
          inheritPath = false;
          text = ''
            crossplane project build

            echo ""
            echo "Setting up test environment..."
            python3 -m venv .venv-test
            .venv-test/bin/pip install --quiet \
              crossplane-function-sdk-python==0.11.0 \
              schemas/python

            # grpcio's C extension needs libstdc++.
            export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

            echo ""
            echo "Running unit tests..."
            failed=0
            for fn in functions/compose-*; do
              echo ""
              echo "--- ''${fn} ---"
              if [ -d "''${fn}/tests" ]; then
                (cd "$fn" && ../../.venv-test/bin/python -m unittest discover -s tests -v) || failed=1
              else
                echo "  (no tests)"
              fi
            done

            if [ "$failed" -ne 0 ]; then
              echo ""
              echo "FAIL: some tests failed"
              exit 1
            fi
          '';
        }
      );
    };

  # Push the Crossplane project to a registry.
  #
  # Auto-generates a dev version tag from git metadata:
  #   v0.1.0-dev.<commit-count>.g<short-hash>
  #
  # Pass --tag to override, e.g.:
  #   nix run .#push-crossplane -- --tag v0.1.0
  pushCrossplane =
    { crossplane, dockerCredentialUp }:
    {
      type = "app";
      meta.description = "Push the Crossplane project to a registry";
      program = pkgs.lib.getExe (
        pkgs.writeShellApplication {
          name = "modelplane-push-crossplane";
          runtimeInputs = [
            crossplane
            dockerCredentialUp
            pkgs.git
          ];
          inheritPath = false;
          text = ''
            # Auto-generate a dev tag from git metadata unless --tag is
            # passed explicitly.
            if [[ ! " $* " =~ " --tag " ]]; then
              count=$(git rev-list --count HEAD)
              hash=$(git rev-parse --short HEAD)
              tag="v0.1.0-dev.''${count}.g''${hash}"
              echo "Pushing with tag: $tag"
              set -- --tag "$tag" "$@"
            fi
            crossplane project push "$@"
          '';
        }
      );
    };

}
