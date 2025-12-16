' VBScript to run IT-invent Bot invisibly
' Запуск бота IT-invent в невидимом режиме

Dim objShell, objFSO, scriptDir

Set objShell = CreateObject("Wscript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Get the directory where this script is located
scriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)

' Change to script directory and run bot
objShell.CurrentDirectory = scriptDir
objShell.Run "python -m bot.main", 0, False

Set objShell = Nothing
Set objFSO = Nothing
