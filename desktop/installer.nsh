!macro customInstall
  ; Shell shortcut resolution can fail immediately after a silent upgrade.
  ; electron-builder still creates the user's shortcuts and launches as that
  ; user; only its post-install launch target changes to the installed binary.
  StrCpy $launchLink "$INSTDIR\${APP_EXECUTABLE_FILENAME}"
!macroend
