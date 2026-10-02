// Main-process-only update controller. The feed is fixed by app-update.yml.
function createUpdater({updater, enabled, version, notify = () => {}, prepareInstall, recoverInstall = async () => {}}) {
  let state = {status: enabled ? 'idle' : 'unsupported', currentVersion: version, version: '', percent: 0, message: enabled ? 'Check for a new Windows release.' : 'Updates are available in the installed Windows app.'};
  let operation = false;
  let installPrepared = false;
  const set = value => { state = {...state, ...value}; notify({...state}); return {...state}; };
  updater.autoDownload = false;
  updater.autoInstallOnAppQuit = false;
  updater.allowPrerelease = false;
  updater.allowDowngrade = false;
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
  updater.on('update-available', info => set({status: 'available', version: info.version, percent: 0, message: `Version ${info.version} is available.`}));
  updater.on('update-not-available', () => set({status: 'current', version: '', percent: 0, message: 'You have the latest published version.'}));
  updater.on('download-progress', progress => set({status: 'downloading', percent: Math.max(0, Math.min(100, Number(progress.percent) || 0)), message: 'Downloading update…'}));
  updater.on('update-downloaded', info => set({status: 'downloaded', version: info.version, percent: 100, message: 'Update ready. Restart when your work is finished.'}));
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
        updater.quitAndInstall(false, true);
      } catch (error) {
        if (installPrepared) { installPrepared = false; await recoverInstall(); }
        set({status: 'downloaded', message: error.message || 'Finish the current job before installing.'});
      } finally { operation = false; }
      return {...state};
    },
  };
}
module.exports = {createUpdater};
