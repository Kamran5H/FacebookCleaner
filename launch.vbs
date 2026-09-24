' Facebook Zenith Cleaner - Resilient Native Launcher
Option Explicit

Dim shell, fso, appDir, pythonExe, script, cmd, i, candidates, cand, pyCandidates

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
If Not fso.FileExists(appDir & "\backend\app.py") Then
    candidates = Array( _
        "C:\Users\chkam\OneDrive\Desktop\BrandFinder\FacebookCleaner", _
        "C:\Users\chkam\OneDrive\Desktop\FacebookCleaner", _
        "C:\Users\chkam\Desktop\BrandFinder\FacebookCleaner" _
    )
    For Each cand In candidates
        If fso.FileExists(cand & "\backend\app.py") Then
            appDir = cand
            Exit For
        End If
    Next
End If

shell.CurrentDirectory = appDir
script = appDir & "\backend\app.py"

pyCandidates = Array( _
    shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python314\pythonw.exe", _
    shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python314\python.exe", _
    "C:\Users\chkam\AppData\Local\Programs\Python\Python314\pythonw.exe", _
    "C:\Users\chkam\AppData\Local\Programs\Python\Python314\python.exe", _
    "pythonw.exe", _
    "python.exe")

pythonExe = ""
For i = 0 To UBound(pyCandidates)
    If pythonExe = "" And fso.FileExists(pyCandidates(i)) Then pythonExe = pyCandidates(i)
Next

If pythonExe = "" Then pythonExe = "python.exe"

cmd = Chr(34) & pythonExe & Chr(34) & " " & Chr(34) & script & Chr(34) & " --open"

On Error Resume Next
shell.Run cmd, 0, False
If Err.Number <> 0 Then
    Err.Clear
    shell.Run "cmd.exe /c python " & Chr(34) & script & Chr(34) & " --open", 0, False
End If
On Error GoTo 0
