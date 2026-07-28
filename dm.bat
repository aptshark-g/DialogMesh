@echo off
set PYTHONPATH=%~dp0..
python -m core.agent.cli.entry %*
