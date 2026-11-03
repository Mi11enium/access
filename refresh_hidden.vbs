' Запускает refresh.bat без окна консоли (для Планировщика задач Windows).
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
sh.Run """" & fso.GetParentFolderName(WScript.ScriptFullName) & "\refresh.bat"" --publish", 0, False
