const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

function backendCandidates(context) {
  const candidates = [];
  const platform = context?.electronPlatformName || process.platform;
  const appOutDir = context?.appOutDir;

  if (appOutDir) {
    if (platform === "darwin") {
      const productName = context.packager.appInfo.productFilename;
      candidates.push(
        path.join(appOutDir, `${productName}.app`, "Contents", "Resources", "backend", "bdgen-server"),
      );
    } else if (platform === "linux") {
      candidates.push(path.join(appOutDir, "resources", "backend", "bdgen-server"));
    } else if (platform === "win32") {
      candidates.push(path.join(appOutDir, "resources", "backend", "bdgen-server.exe"));
    }
  }

  candidates.push(
    path.resolve(__dirname, "../../../build/backend/bdgen-server"),
    path.resolve(__dirname, "../../../build/backend/bdgen-server.exe"),
  );

  return candidates;
}

function prepareBackendResource(context) {
  const platform = context?.electronPlatformName || process.platform;
  const backend = backendCandidates(context).find((candidate) => fs.existsSync(candidate));

  if (!backend) {
    throw new Error("Bundled backend executable was not found.");
  }

  if (platform !== "win32") {
    fs.chmodSync(backend, 0o755);
  }

  if (platform === "darwin") {
    execFileSync("codesign", ["--force", "--sign", "-", backend], {
      stdio: "inherit",
    });

    // Sign the entire .app bundle so macOS Gatekeeper doesn't reject it as "damaged".
    if (context?.appOutDir) {
      const productName = context.packager.appInfo.productFilename;
      const appBundle = path.join(context.appOutDir, `${productName}.app`);
      if (fs.existsSync(appBundle)) {
        // Remove extended attributes (Finder metadata) that block codesigning.
        execFileSync("xattr", ["-cr", appBundle], { stdio: "inherit" });
        execFileSync("codesign", ["--force", "--deep", "--sign", "-", appBundle], {
          stdio: "inherit",
        });
      }
    }
  }
}

module.exports = prepareBackendResource;

if (require.main === module) {
  prepareBackendResource();
}
