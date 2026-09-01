' Facebook Zenith Cleaner - launcher
'
' Starts the local server (silently, no console window) and lets the server
' itself open the dashboard once the port is actually listening. The old
' version guessed with a fixed 1-second sleep and opened a second window when
' the app was already running.

Option Explicit

Dim shell, fso, appDir, pythonExe, script, cmd, i, candidates

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = appDir

script = appDir & "\backend\app.py"
If Not fso.FileExists(script) Then
    MsgBox "Cannot find:" & vbCrLf & script, vbCritical, "Facebook Zenith Cleaner"
    WScript.Quit 1
End If

' Prefer pythonw.exe so no black console window flashes up.
candidates = Array( _
    shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python314\pythonw.exe", _
    shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python313\pythonw.exe", _
    shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\pythonw.exe", _
    shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python311\pythonw.exe", _
    "C:\Program Files\Python314\pythonw.exe", _
    "C:\Program Files\Python313\pythonw.exe")

pythonExe = ""
For i = 0 To UBound(candidates)
    If pythonExe = "" And fso.FileExists(candidates(i)) Then pythonExe = candidates(i)
Next

If pythonExe = "" Then pythonExe = "pythonw.exe"   ' fall back to PATH

' --open makes the server wait for its own port, then open the dashboard as an
' app window. If an instance is already running it just focuses that one.
cmd = Chr(34) & pythonExe & Chr(34) & " " & Chr(34) & script & Chr(34) & " --open"

On Error Resume Next
shell.Run cmd, 0, False
If Err.Number <> 0 Then
    Err.Clear
    shell.Run "cmd.exe /c python " & Chr(34) & script & Chr(34) & " --open", 0, False
    If Err.Number <> 0 Then
        MsgBox "Could not start Python." & vbCrLf & vbCrLf & _
               "Install Python 3.11+ and run setup.bat once.", vbCritical, _
               "Facebook Zenith Cleaner"
    End If
End If
On Error GoTo 0
