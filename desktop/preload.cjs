const {contextBridge, ipcRenderer} = require('electron');
contextBridge.exposeInMainWorld('desktop', Object.freeze({
  getSettings: () => ipcRenderer.invoke('desktop:settings'),
  getCloudState: () => ipcRenderer.invoke('desktop:cloud-state'),
  configureCloud: value => ipcRenderer.invoke('desktop:cloud-configure', value),
  signInCloud: value => ipcRenderer.invoke('desktop:cloud-sign-in', value),
  signOutCloud: () => ipcRenderer.invoke('desktop:cloud-sign-out'),
  getCloudWorkspaces: () => ipcRenderer.invoke('desktop:cloud-workspaces'),
  joinCloudWorkspace: input => ipcRenderer.invoke('desktop:cloud-join',input),
  setCloudMember: input => ipcRenderer.invoke('desktop:cloud-member',input),
  disconnectCloudWorkspace: () => ipcRenderer.invoke('desktop:cloud-disconnect'),
  getCloudWorkerIdentity: () => ipcRenderer.invoke('desktop:cloud-worker-identity'),
  createCloudWorkspace: () => ipcRenderer.invoke('desktop:cloud-create-workspace'),
  runCloudAction: value => ipcRenderer.invoke('desktop:cloud-action', value),
  getPreferences: () => ipcRenderer.invoke('desktop:preferences'),
  savePreferences: value => ipcRenderer.invoke('desktop:save-preferences', value),
  getUpdateState: () => ipcRenderer.invoke('desktop:update-state'),
  checkForUpdates: () => ipcRenderer.invoke('desktop:update-check'),
  downloadUpdate: () => ipcRenderer.invoke('desktop:update-download'),
  installUpdate: () => ipcRenderer.invoke('desktop:update-install'),
  onUpdateState: callback => {
    const listener = (_, state) => callback(state);
    ipcRenderer.on('desktop:update-state', listener);
    return () => ipcRenderer.removeListener('desktop:update-state', listener);
  },
  saveSettings: value => ipcRenderer.invoke('desktop:save-settings', value),
  discardSettings: () => ipcRenderer.invoke('desktop:discard-settings'),
  importServiceAccount: () => ipcRenderer.invoke('desktop:import-account'),
  chooseBrowser: () => ipcRenderer.invoke('desktop:choose-browser'),
  openDataFolder: () => ipcRenderer.invoke('desktop:open-data'),
  backup: password => ipcRenderer.invoke('desktop:backup', password),
  restoreBackup: password => ipcRenderer.invoke('desktop:restore', password),
  onCommand: callback => {
    const listener = (_, command) => callback(command);
    ipcRenderer.on('desktop:command', listener);
    return () => ipcRenderer.removeListener('desktop:command', listener);
  },
}));
