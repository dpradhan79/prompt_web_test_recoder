"""
constant default model for the application
"""
import os
from pathlib import Path

# other constants can be added here as needed
# get the parent folder of the project

file_sep_char = os.sep

PARENT_DIR = Path(__file__).parents[1]
LOG_FOLDER = os.path.join(PARENT_DIR, 'Logs')
LOG_FILE = os.path.join(LOG_FOLDER, 'app.log')
SCHEMA_FOLDER = os.path.join(PARENT_DIR, 'artifacts')
SCHEMA_FILE = os.path.join(SCHEMA_FOLDER, 'output_schema_1.json')
