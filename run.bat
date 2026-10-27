@echo off
REM 四川旅游 GraphRAG

echo 四川旅游 GraphRAG

if not exist venv (
    echo 创建虚拟环境...
    python -m venv venv
)

echo 激活虚拟环境...
call venv\Scripts\activate.bat

if not exist venv\Lib\site-packages\fastapi (
    echo 安装依赖...
    pip install -r requirements.txt
)

:menu
cls
echo.
echo ====== 四川旅游 GraphRAG ======
echo.
echo  [1] 启动 Web            python run.py web
echo  [2] 命令行问答          python run.py chat
echo  [3] 导入知识图谱        python run.py import
echo  [4] 黄金集评测          python run.py eval
echo  [5] 运行单测
echo  [0] 退出
echo.

set /p choice=请选择 (0-5):

if "%choice%"=="1" (
    python run.py web
    pause
    goto menu
)
if "%choice%"=="2" (
    python run.py chat
    goto menu
)
if "%choice%"=="3" (
    python run.py import
    pause
    goto menu
)
if "%choice%"=="4" (
    python run.py eval
    pause
    goto menu
)
if "%choice%"=="5" (
    python -m unittest tests.test_enricher tests.test_nlu_graph tests.test_offline
    pause
    goto menu
)
if "%choice%"=="0" (
    goto end
) else (
    echo 输入错误
    timeout /t 2 >nul
    goto menu
)

:end
deactivate
