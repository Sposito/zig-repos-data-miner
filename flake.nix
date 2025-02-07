{
  description = "Zig Repository Graph Analysis Dev Shell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs =
    { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        buildInputs = [
          pkgs.python311
          pkgs.python311Packages.fastapi
          pkgs.python311Packages.networkx
          pkgs.python311Packages.uvicorn
          pkgs.python311Packages.pandas
          pkgs.python311Packages.gitpython
          pkgs.python311Packages.virtualenv
          pkgs.python311Packages.pytest
          pkgs.jetbrains.pycharm-community-src
          pkgs.git
        ];

        shellHook = ''
          echo "Zig Repository Graph Analysis Dev Shell Loaded"
        '';
      };
    };
}
