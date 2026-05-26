@echo off
REM --------------------------------------
REM Batch script for running Python scripts with error logging
REM Version: 1.1
REM Last Updated: 2024-12-11
REM Author: [Your Name or Team]
REM --------------------------------------

REM Configure environment variables
set LOG_DIR=C:\Users\admin\Documents\BI_Analytics\Logistics\logs
set SCRIPT_DIR=C:\Users\admin\Documents\BI_Analytics\Logistics
set LOG_FILE=%LOG_DIR%\execution_log.txt
set ERROR_LOG_FILE=%LOG_DIR%\error_log.txt

REM Ensure log directory exists
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM Log start time
echo [INFO] %DATE% %TIME% - Batch script execution started >> "%LOG_FILE%"

REM Navigate to script directory
echo [INFO] %DATE% %TIME% - Navigating to script directory: %SCRIPT_DIR% >> "%LOG_FILE%"
cd /d "%SCRIPT_DIR%"
if errorlevel 1 (
    echo [ERROR] %DATE% %TIME% - Failed to navigate to script directory >> "%ERROR_LOG_FILE%"
    echo [ERROR] Could not change to directory: %SCRIPT_DIR%. Check the path.
    exit /b 1
)

REM Activate virtual environment
echo [INFO] %DATE% %TIME% - Activating virtual environment >> "%LOG_FILE%"
call .venv\Scripts\activate
if errorlevel 1 (
    echo [ERROR] %DATE% %TIME% - Failed to activate virtual environment >> "%ERROR_LOG_FILE%"
    echo [ERROR] Could not activate virtual environment. Check if '.venv' exists and is configured correctly.
    exit /b 1
)

REM Execute Python script: C2M_xlsx_search_asyncio.py
echo [INFO] %DATE% %TIME% - Executing script: C2M_xlsx_search_asyncio.py >> "%LOG_FILE%"
python C2M_xlsx_search_asyncio.py
if errorlevel 1 (
    echo [ERROR] %DATE% %TIME% - Error during execution of C2M_xlsx_search_asyncio.py >> "%ERROR_LOG_FILE%"
    echo [ERROR] Script 'C2M_xlsx_search_asyncio.py' encountered an error. Check the script and its dependencies.
    deactivate
    exit /b 1
)

REM Execute Python script: C2M_excel_to_manifest.py
echo [INFO] %DATE% %TIME% - Executing script: C2M_excel_to_manifest.py >> "%LOG_FILE%"
python C2M_excel_to_manifest.py
if errorlevel 1 (
    echo [ERROR] %DATE% %TIME% - Error during execution of C2M_excel_to_db.py >> "%ERROR_LOG_FILE%"
    echo [ERROR] Script 'C2M_excel_to_db.py' encountered an error. Check the script and its dependencies.
    deactivate
    exit /b 1
)

REM Execute Python script: cainiao_for_DM.py
echo [INFO] %DATE% %TIME% - Executing script: cainiao_for_DM.py >> "%LOG_FILE%"
python cainiao_for_DM.py
if errorlevel 1 (
    echo [ERROR] %DATE% %TIME% - Error during execution of cainiao_for_DM.py >> "%ERROR_LOG_FILE%"
    echo [ERROR] Script 'cainiao_for_DM.py' encountered an error. Check the script and its dependencies.
    deactivate
    exit /b 1
)

REM Deactivate virtual environment
echo [INFO] %DATE% %TIME% - Deactivating virtual environment >> "%LOG_FILE%"
deactivate
if errorlevel 1 (
    echo [ERROR] %DATE% %TIME% - Failed to deactivate virtual environment >> "%ERROR_LOG_FILE%"
    echo [ERROR] Deactivation of virtual environment failed. Ensure no conflicting processes are running.
    exit /b 1
)

REM Log successful completion
echo [INFO] %DATE% %TIME% - Batch script execution completed successfully >> "%LOG_FILE%"
exit /b 0
