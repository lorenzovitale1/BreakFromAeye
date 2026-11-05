' Avvia Eye Gaze senza alcuna finestra di comando (doppio clic).
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
If Not fso.FileExists(dir & "\.venv\Scripts\pythonw.exe") Then
  MsgBox "Ambiente non trovato: esegui prima setup.bat", 48, "Eye Gaze"
Else
  args = ""
  For Each a In WScript.Arguments
    args = args & " " & a
  Next
  sh.Run """" & dir & "\.venv\Scripts\pythonw.exe"" -m eyegaze" & args, 0, False
End If
