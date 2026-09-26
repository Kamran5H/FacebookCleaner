' Facebook Zenith Cleaner - silent desktop launcher
' Starts backend\app.py with a windowless Python so only the dashboard appears.
' Works from wherever the folder lives: nothing here is tied to one user's PC.
Option Explicit

Dim shell, fso, appDir, script, pythonExe, localApp, cmd

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
script = appDir & "\backend\app.py"

If Not fso.FileExists(script) Then
    MsgBox "Could not find backend\app.py next to this launcher:" & vbCrLf & appDir & vbCrLf & vbCrLf & _
           "Keep launch.vbs inside the FacebookCleaner folder and re-run setup.bat.", _
           vbCritical, "Facebook Zenith Cleaner"
    WScript.Quit 1
End If

shell.CurrentDirectory = appDir
localApp = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%")

' 1) The project's own virtual environment (README install path).
pythonExe = FirstExisting(Array( _
    appDir & "\.venv\Scripts\pythonw.exe", _
    appDir & "\venv\Scripts\pythonw.exe"))

' 2) The newest per-user python.org install (Python3xx folders).
If pythonExe = "" Then pythonExe = NewestPythonIn(localApp & "\Programs\Python")

' 3) The "py" launcher, then whatever is on PATH.
If pythonExe = "" Then pythonExe = FirstExisting(Array(shell.ExpandEnvironmentStrings("%WINDIR%") & "\pyw.exe"))
If pythonExe = "" Then pythonExe = "pythonw.exe"

cmd = Chr(34) & pythonExe & Chr(34) & " " & Chr(34) & script & Chr(34) & " --open"

On Error Resume Next
shell.Run cmd, 0, False
If Err.Number <> 0 Then
    Err.Clear
    ' Last resort: a visible console so any error message can actually be read.
    shell.Run "cmd.exe /k python " & Chr(34) & script & Chr(34) & " --open", 1, False
    If Err.Number <> 0 Then
        MsgBox "Python was not found. Install Python 3.10+ and run setup.bat first.", _
               vbCritical, "Facebook Zenith Cleaner"
    End If
End If
On Error GoTo 0


Function FirstExisting(paths)
    Dim p
    FirstExisting = ""
    For Each p In paths
        If fso.FileExists(p) Then
            FirstExisting = p
            Exit Function
        End If
    Next
End Function

Function NewestPythonIn(root)
    Dim folder, pyDir, best, bestVer, ver
    NewestPythonIn = ""
    If Not fso.FolderExists(root) Then Exit Function
    Set folder = fso.GetFolder(root)
    bestVer = -1
    For Each pyDir In folder.SubFolders
        ' Python312, Python313, Python314 ...
        ver = Replace(Replace(LCase(pyDir.Name), "python", ""), "-32", "")
        If IsNumeric(ver) And fso.FileExists(pyDir.Path & "\pythonw.exe") Then
            If CLng(ver) > bestVer Then
                bestVer = CLng(ver)
                best = pyDir.Path & "\pythonw.exe"
            End If
        End If
    Next
    If bestVer >= 0 Then NewestPythonIn = best
End Function
