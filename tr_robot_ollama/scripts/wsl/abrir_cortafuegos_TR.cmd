@echo off
rem ================================================================
rem  TR - Abrir el cortafuegos de WSL para ROS 2
rem  Doble clic aqui y pulsa "Si" en el aviso de Windows.
rem  Ejecuta preparar_windows.ps1 como administrador (una sola vez).
rem ================================================================
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -NoExit -File \"%~dp0preparar_windows.ps1\"'"
