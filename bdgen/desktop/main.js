const { app, BrowserWindow, Menu, dialog, ipcMain } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const path = require("path");

let backend = null;
let backendLaunchError = null;
let backendExecutable = null;
let mainWindow = null;
let isQuitting = false;

async function createWindow() {
  const port = await findFreePort();
  const appData = app.getPath("userData");
  const outputRoot = path.join(app.getPath("documents"), "BdGEN");
  const icon = resolveWindowIcon();

  await startBackend({ port, appData, outputRoot });
  await waitForHealth(port);

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    frame: false,
    titleBarStyle: "hidden",
    autoHideMenuBar: true,
    backgroundColor: "#fbf8f3",
    icon,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.on("maximize", () => mainWindow.webContents.send("window:maximized", true));
  mainWindow.on("unmaximize", () => mainWindow.webContents.send("window:maximized", false));

  await mainWindow.loadURL(`http://127.0.0.1:${port}/`);
}

async function startBackend({ port, appData, outputRoot }) {
  const exe = resolveBackendExecutable();
  backendExecutable = exe;
  backendLaunchError = null;
  const env = {
    ...process.env,
    BDGEN_HOST: "127.0.0.1",
    BDGEN_PORT: String(port),
    BDGEN_CONFIG_ROOT: appData,
    BDGEN_OUTPUT_ROOT: outputRoot,
  };

  backend = spawn(exe.command, exe.args, {
    cwd: exe.cwd || undefined,
    env,
    windowsHide: true,
    stdio: "pipe",
  });

  backend.stdout.on("data", (data) => console.log(`[backend] ${data}`));
  backend.stderr.on("data", (data) => console.error(`[backend] ${data}`));
  backend.on("error", (err) => {
    backendLaunchError = err;
    console.error(`[backend] failed to start ${exe.command}: ${err.message}`);
  });
  backend.on("exit", (code, signal) => {
    const expectedStop = isQuitting || backend?.killed || signal === "SIGTERM";
    if (!expectedStop && code !== 0 && mainWindow && !mainWindow.isDestroyed()) {
      dialog.showErrorBox("BdGEN", `Le serveur local s'est arrete (code ${code}).`);
    }
  });
}

function resolveBackendExecutable() {
  if (process.env.BDGEN_BACKEND_CMD) {
    return {
      command: process.env.BDGEN_BACKEND_CMD,
      args: (process.env.BDGEN_BACKEND_ARGS || "").split(" ").filter(Boolean),
    };
  }

  const resources = process.resourcesPath || path.join(__dirname, "..");
  const bundled = path.join(resources, "backend", process.platform === "win32" ? "bdgen-server.exe" : "bdgen-server");
  if (fs.existsSync(bundled)) {
    return { command: bundled, args: [] };
  }

  return {
    command: process.platform === "win32" ? "python" : "python3",
    args: ["-m", "bdgen.server"],
    cwd: path.resolve(__dirname, ".."),
  };
}

function resolveWindowIcon() {
  let iconFile = "icon.png";
  if (process.platform === "win32") {
    iconFile = "icon.ico";
  } else if (process.platform === "darwin") {
    iconFile = "icon.icns";
  }
  const candidates = [
    path.join(__dirname, "assets", iconFile),
    path.join(process.resourcesPath || path.join(__dirname, ".."), "assets", iconFile),
    path.join(__dirname, "assets", "icon.png"),
    path.join(process.resourcesPath || path.join(__dirname, ".."), "assets", "icon.png"),
  ];

  return candidates.find((candidate) => fs.existsSync(candidate));
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close(() => resolve(address.port));
    });
    server.on("error", reject);
  });
}

async function waitForHealth(port) {
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    if (backendLaunchError) {
      throw new Error(formatBackendLaunchError(backendLaunchError, backendExecutable));
    }
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/health`);
      if (res.ok) return;
    } catch {
      // Backend is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error("Le serveur BdGEN n'a pas demarre a temps.");
}

function formatBackendLaunchError(err, exe) {
  const command = exe?.command || "bdgen-server";
  if (err.code === "EACCES") {
    return `Le serveur local n'est pas executable: ${command}`;
  }
  if (err.code === "ENOENT") {
    return `Le serveur local est introuvable: ${command}`;
  }
  return `Le serveur local n'a pas pu demarrer (${err.code || "erreur inconnue"}): ${err.message}`;
}

app.whenReady().then(() => {
  Menu.setApplicationMenu(null);
  registerWindowControls();

  createWindow().catch((err) => {
    dialog.showErrorBox("BdGEN", err.message || String(err));
    app.quit();
  });
});

function registerWindowControls() {
  ipcMain.handle("window:minimize", () => {
    BrowserWindow.getFocusedWindow()?.minimize();
  });

  ipcMain.handle("window:toggleMaximize", () => {
    const window = BrowserWindow.getFocusedWindow();
    if (!window) return false;
    if (window.isMaximized()) {
      window.unmaximize();
      return false;
    }
    window.maximize();
    return true;
  });

  ipcMain.handle("window:close", () => {
    BrowserWindow.getFocusedWindow()?.close();
  });

  ipcMain.handle("window:isMaximized", () => {
    return BrowserWindow.getFocusedWindow()?.isMaximized() || false;
  });
}

app.on("before-quit", () => {
  isQuitting = true;
  if (backend && !backend.killed) {
    backend.kill();
  }
});

app.on("window-all-closed", () => {
  app.quit();
});
