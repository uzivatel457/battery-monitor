' Spusteni BatteryMonitoru bez okna CMD
Option Explicit
Dim shell, fso, folder, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder

If Not fso.FileExists(folder & "\.portable") Then
  shell.Run "cmd /c """ & folder & "\install.bat""", 1, True
End If

If shell.Run("where pyw", 0, True) = 0 Then
  cmd = "pyw -3 """ & folder & "\main.py"""
ElseIf shell.Run("where pythonw", 0, True) = 0 Then
  cmd = "pythonw """ & folder & "\main.py"""
ElseIf shell.Run("where py", 0, True) = 0 Then
  cmd = "py -3 """ & folder & "\main.py"""
ElseIf shell.Run("where python", 0, True) = 0 Then
  cmd = "python """ & folder & "\main.py"""
Else
  MsgBox "Python 3 was not found. Run install.bat first." & vbCrLf & "Python 3 nebyl nalezen. Spustte nejdrive install.bat.", vbCritical, "Battery monitor by u457"
  WScript.Quit 1
End If

shell.Run cmd, 0, False
