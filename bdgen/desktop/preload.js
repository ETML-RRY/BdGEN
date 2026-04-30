const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("bdgenDesktop", {
  platform: process.platform,
});
