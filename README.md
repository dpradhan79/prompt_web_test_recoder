# prompt_web_test_recoder

Test follows prompt, navigates web, validates and produces traces of navigation and test verification in structured json format. Supports both headed and headless navigation. Author - Debasish Pradhan

### Pre-requisite -

#### 1. pip


### - Virtual Environment

- py -m venv .venv [create virtual environment (local sandbox)]
  Command - .venv/Scripts/activate.bat [for pip, this step is mandatory for activating virtual environment]
  pip install -r requirements.txt [installation of module dependencies as per file - requirements.txt]

#### 2. uv

- pip install uv
  uv sync --link-mode=copy

#### 

3. Browser Installation For Playwright - Chromium/Firefox/Webkit

   - command from root folder - "playwright install" [use this command from project root folder after installing packages in activated virtual environment. (U should see .venv in your command prompt or pyproject.toml project name in case uv is used)

   1. Troubleshooting

      - some modules not installed due to error -  hardlinking may not be supporte
        - delete .venv folder (virtual environment folder)
        - Apply command - uv sync --link-mode=copy
      - To Use Particular Python Version
        - update pyproject.toml -> requires-python
        - Apply command - uv pin python <x.y> ex - uv pin python 3.11
