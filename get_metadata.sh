#!/bin/bash

# Check if two arguments are provided
if [ $# -lt 2 ]; then
    echo "Error: Please provide the project folder path and the classes path as arguments"
    echo "Usage: ./get_metadata.sh <folder_path> <classes_path>"
    exit 1
fi

# Get the folder path from command line argument
PROJECT_DIR="$1"
CLASS_DIR="$2"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER_DATA_DIR="$SCRIPT_DIR/python_stuff/helper_data"
CG_DIR="$SCRIPT_DIR/sootup_cg"

echo "Running Call Graph Generator"
mvn -f "$CG_DIR/pom.xml" clean compile
mvn -f "$CG_DIR/pom.xml" exec:java -Dexec.mainClass=CallGraphGenerator -Dexec.args="$CLASS_DIR $HELPER_DATA_DIR"

echo "Switching Directories"
cd "$SCRIPT_DIR/python_stuff" || { echo "Directory not found"; exit 1; }

echo "Running Code Parser"
python preprocessing.py "$PROJECT_DIR"

echo "Generating Call Graph JSON"
python generate_callgraph.py

echo "Generating Metadata"
python generate_metadata.py
