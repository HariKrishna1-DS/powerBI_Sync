const {contextBridge, ipcRenderer} = require('electron');
contextBridge.exposeInMainWorld('desktop', Object.freeze({
  getSettings: () => ipcRenderer.invoke('desktop:settings'),
  saveSettings: value => ipcRenderer.invoke('desktop:save-settings', value),
  discardSettings: () => ipcRenderer.invoke('desktop:discard-settings'),
  importServiceAccount: () => ipcRenderer.invoke('desktop:import-account'),
  chooseBrowser: () => ipcRenderer.invoke('desktop:choose-browser'),
  openDataFolder: () => ipcRenderer.invoke('desktop:open-data'),
  backup: () => ipcRenderer.invoke('desktop:backup'),
  restoreBackup: () => ipcRenderer.invoke('desktop:restore'),
  onCommand: callback => {
    const listener = (_, command) => callback(command);
    ipcRenderer.on('desktop:command', listener);
    return () => ipcRenderer.removeListener('desktop:command', listener);
  },
}));
