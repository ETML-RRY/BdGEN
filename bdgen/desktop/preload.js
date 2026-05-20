const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("bdgenDesktop", {
  platform: process.platform,
  minimize: () => ipcRenderer.invoke("window:minimize"),
  toggleMaximize: () => ipcRenderer.invoke("window:toggleMaximize"),
  close: () => ipcRenderer.invoke("window:close"),
  isMaximized: () => ipcRenderer.invoke("window:isMaximized"),
  openExternal: (url) => ipcRenderer.invoke("app:openExternal", url),
  getPreference: (key) => ipcRenderer.invoke("preferences:get", key),
  setPreference: (key, value) => ipcRenderer.invoke("preferences:set", key, value),
  onMaximizedChange: (callback) => {
    const listener = (_event, value) => callback(Boolean(value));
    ipcRenderer.on("window:maximized", listener);
    return () => ipcRenderer.removeListener("window:maximized", listener);
  },
});
