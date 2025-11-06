@echo off
for /f "tokens=*" %%i in ('ipconfig ^| findstr /C:"IPv4 Address"') do set ipVariable=%%i
REM Strip "IPv4 Address. . . . . . . . . . . :" from the variable
set ipVariable=%ipVariable:*: =%
python manage.py runserver %ipVariable%:8000
