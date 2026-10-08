// Main-process-only updater. Stable releases follow GitHub's Latest designation.
const PRODUCTION_UPDATE_FEED=Object.freeze({provider:'github',owner:'HariKrishna1-DS',repo:'powerBI_Sync',private:false});
function createUpdater({updater, enabled, version, notify = () => {}, prepareInstall, recoverInstall = async () => {}}) {
  let state = {status: enabled ? 'idle' : 'unsupported', currentVersion: version, version: '', percent: 0, lastChecked: null, message: enabled ? 'Check for a new Windows release.' : 'Updates are available in the installed Windows app.'};
  let operation = false;
  let installPrepared = false;
  const set = value => { state = {...state, ...value}; notify({...state}); return {...state}; };
  if (enabled) updater.setFeedURL({...PRODUCTION_UPDATE_FEED});
  updater.autoDownload = false;
  updater.autoInstallOnAppQuit = false;
  updater.allowPrerelease = false;
  updater.allowDowngrade = false;
  updater.disableWebInstaller = true;
  // Never include request URLs, headers, or release bodies in user-visible errors.
  updater.logger = {info() {}, warn() {}, error() {}, debug() {}};
  function failure(error) {
    if (installPrepared) {
      installPrepared = false;
      Promise.resolve().then(recoverInstall).catch(() => set({status: 'error', message: 'Installation failed. Reopen Tv Tracker to restart the local engine.'}));
    }
    const raw = String(error?.code || '') + ' ' + String(error?.message || '');
    const message = /404|No published versions|ERR_UPDATER_LATEST_VERSION_NOT_FOUND|ERR_UPDATER_CHANNEL_FILE_NOT_FOUND/i.test(raw)
      ? 'No Windows update is published yet. Try again after the next release.'
      : /403|429/.test(raw) ? 'GitHub is limiting requests. Please try again later.'
      : /sha512|checksum|signature/i.test(raw) ? 'Update verification failed. Nothing was installed. Check again and retry the download.'
      : 'Could not reach or download the update. Check your internet connection and try again.';
    return set({status: 'error', message, percent: 0});
  }
  updater.on('error', failure);
  updater.on('update-available', info => set({status: 'available', version: info.version, percent: 0, lastChecked: new Date().toISOString(), message: `Version ${info.version} is available.`}));
  updater.on('update-not-available', info => {
    const stable = value => /^\d+\.\d+\.\d+$/.test(value || '');
    const newer = stable(version) && stable(info?.version) && version.split('.').map(Number).some((part, i, parts) => part > Number(info.version.split('.')[i]) && parts.slice(0, i).every((p, j) => p === Number(info.version.split('.')[j])));
    set({status: 'current', version: '', percent: 0, lastChecked: new Date().toISOString(), message: newer ? `Version ${version} is installed. GitHub currently publishes ${info.version}; no newer update is available.` : 'You have the latest published version.'});
  });
  updater.on('download-progress', progress => set({status: 'downloading', percent: Math.max(0, Math.min(100, Number(progress.percent) || 0)), message: 'Downloading update…'}));
  updater.on('update-downloaded', info => set({status: 'downloaded', version: info.version, percent: 100, message: 'Download complete. Choose Install & open when your work is finished.'}));
  return {
    state: () => ({...state}),
    async check() {
      if (!enabled || operation || ['downloaded', 'installing'].includes(state.status)) return {...state};
      operation = true;
      set({status: 'checking', version: '', percent: 0, message: 'Checking GitHub releases…'});
      try { await updater.checkForUpdates(); } catch (error) { failure(error); }
      finally { operation = false; }
      return {...state};
    },
    async download() {
      if (!enabled || operation || state.status !== 'available') return {...state};
      operation = true;
      set({status: 'downloading', message: 'Starting download…'});
      try { await updater.downloadUpdate(); } catch (error) { failure(error); }
      finally { operation = false; }
      return {...state};
    },
    async install() {
      if (!enabled || operation || state.status !== 'downloaded') return {...state};
      operation = true;
      set({status: 'installing', message: 'Checking that all work has finished…'});
      try {
        await prepareInstall();
        installPrepared = true;
        set({status: 'installing', message: 'Closing Tv Tracker to install the update…'});
        updater.quitAndInstall(true, true);
      } catch (error) {
        if (installPrepared) {
          installPrepared = false;
          try { await recoverInstall(); }
          catch { return set({status: 'error', message: 'Installation failed. Reopen Tv Tracker to restart the local engine.'}); }
        }
        set({status: 'downloaded', message: error.message || 'Finish the current job before installing.'});
      } finally { operation = false; }
      return {...state};
    },
  };
}

// Start after the workspace is usable. Failed checks retry later without popups;
// an offered/downloaded update stays available until the user acts on it.
function scheduleUpdateChecks(controller, {delay = setTimeout, clear = clearTimeout, startupMs = 15000, intervalMs = 6 * 60 * 60 * 1000, retryMs = 15 * 60 * 1000} = {}) {
  let stopped = false, timer;
  const schedule = ms => { if (!stopped) { timer = delay(tick, ms); timer?.unref?.(); } };
  async function tick() {
    if (stopped) return;
    let failed = false;
    try {
      if (['idle', 'current', 'error'].includes(controller.state().status)) await controller.check();
    } catch { failed = true; }
    finally { schedule(failed || controller.state().status === 'error' ? retryMs : intervalMs); }
  }
  schedule(startupMs);
  return () => { stopped = true; clear(timer); };
}
module.exports = {createUpdater, scheduleUpdateChecks, PRODUCTION_UPDATE_FEED};
