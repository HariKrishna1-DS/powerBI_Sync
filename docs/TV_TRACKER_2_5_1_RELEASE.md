# Tv Tracker 2.5.1

This patch includes the 2.5.0 workspace redesign and fixes the final step of a Windows update. The installer launches the installed executable directly after installation. It continues to create the normal Start menu and desktop shortcuts and runs the app as the signed-in user.

During the real 2.4.1 → 2.5.0 update, release detection, downloading, hash verification, automatic backups and binary replacement succeeded. Windows then reported that it could not find the Start menu shortcut used for relaunch, although the installed executable and shortcut were present. The new installer avoids that shortcut-resolution dependency.

No application data, API contracts, dependencies or credential handling changed. The encrypted settings and product preferences were unchanged across the observed upgrade. Use Settings → Updates to install this patch.

The sidebar can also scroll in short desktop windows, keeping Settings and Appearance reachable below the navigation and capture library. A 1280×620 viewport regression covers these controls.

Validation includes the Windows build and regression suites, packaged lifecycle/recovery checks and a real installed-app update. Live TitleVision extraction requires the user's connection details. This release remains unsigned until a Windows signing certificate is configured.
