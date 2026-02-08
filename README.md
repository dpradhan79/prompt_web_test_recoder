# prompt_web_test_recoder

Test follows prompt, navigates web, validates and produces traces of navigation and test verification in structured json format. Supports both headed and headless navigation. Author - Debasish Pradhan

### Pre-requisite -

#### 1. pip

### - Virtual Environment

- py -m venv .venv [create virtual environment (local sandbox)]
  Command - .venv\Scripts\activate.bat [for pip, this step is mandatory for activating virtual environment]
  pip install -r requirements.txt [installation of module dependencies as per file - requirements.txt]

#### 2. uv

- pip install uv
  uv sync --link-mode=copy

#### 

#### 3. Browser Installation For Playwright - Chromium/Firefox/Webkit

- command from root folder - "playwright install" [use this command from project root folder after installing packages in activated virtual environment. (U should see .venv in your command prompt or pyproject.toml project name in case uv is used)
- Note - Under VPN, command may fail due to firewall restrictions, without VPN connection, it may work
- browser specific installation -

  - "playwright install {x}" [x = chromium|firefox|webkit]
  - for headless - "playwright install --only-shell chromium"

#### Troubleshooting

- some modules not installed due to error -  hardlinking may not be supported

  - delete .venv folder (virtual environment folder)
  - Apply command - uv sync --link-mode=copy
- delete .venv folder (virtual environment folder)
- Apply command - uv sync --link-mode=copy
- To Use Particular Python Version

  - update pyproject.toml -> requires-python
  - Apply command - uv pin python <x.y> ex - uv pin python 3.11
- ensure you have .env file in root folder and you have key for variable/value for LLM secret key

  - API_KEY=1234
- pip issue/IDE sync issue

  - Try Below commands

    python -m ensurepip --upgrade
    python -m pip install --upgrade pip setuptools wheel
    python -m pip --version
