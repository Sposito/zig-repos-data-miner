#!/usr/bin/env python3
import os
import platform
import subprocess
import re


def get_file_content_with_header(filepath, remove_comments=False):
    """
    Reads the content of the given file, optionally removing comments and docstrings,
    and returns it with a header indicating the file name.
    """
    header = f"--- {os.path.basename(filepath)} ---\n"
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        if remove_comments:
            content = remove_comments_from_code(content)
    except Exception as e:
        content = f"Error reading {filepath}: {e}"
    return header + content + "\n"


def remove_comments_from_code(code):
    """
    Removes all Python comments (# ...) and docstrings (''' ... ''' or \"\"\" ... \"\"\").
    """
    # Remove inline comments (but not in strings)
    code = re.sub(r"(^|\s)#.*", "", code)

    # Remove multiline docstrings (handles both ''' and """)
    code = re.sub(r"(?s)\"\"\".*?\"\"\"|'''.*?'''", "", code)

    return code.strip()


def copy_to_clipboard(text):
    """
    Copies the provided text to the clipboard. Uses pbcopy on macOS and xclip on Linux.
    """
    system = platform.system()
    try:
        if system == "Darwin":
            # macOS
            process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-8'))
        elif system == "Linux":
            # Linux (requires xclip to be installed)
            process = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-8'))
        else:
            print("Clipboard copy is only supported on macOS and Linux.")
            return False
        return True
    except Exception as e:
        print(f"Failed to copy to clipboard: {e}")
        return False


def execute(remove_comments=False):
    # Determine the project root (assumes this script is in the 'scripts' folder)
    script_dir = os.path.dirname(os.path.realpath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, ".."))

    prompt_parts = []

    # 1. Read main.py
    main_file = os.path.join(project_root, "main.py")
    if os.path.exists(main_file):
        prompt_parts.append(get_file_content_with_header(main_file, remove_comments))
    else:
        print("Warning: main.py not found in the project root.")

    # 2. Read all .py files from the tests folder
    tests_dir = os.path.join(project_root, "tests")
    if os.path.isdir(tests_dir):
        for filename in sorted(os.listdir(tests_dir)):
            if filename.endswith(".py"):
                file_path = os.path.join(tests_dir, filename)
                prompt_parts.append(get_file_content_with_header(file_path, remove_comments))
    else:
        print("Warning: tests folder not found in the project root.")

    # 3. Append the extra prompt
    prompt_parts.append("Give me a very brief description of the Situation.")

    final_prompt = "\n".join(prompt_parts)

    # 4. Copy the final prompt to the OS clipboard
    if copy_to_clipboard(final_prompt):
        print("Prompt successfully copied to clipboard.")
    else:
        print("Failed to copy prompt to clipboard. Here is the prompt:\n")
        print(final_prompt)




if __name__ == "__main__":
        execute(True)

# if __name__ == "__main__":
#     execute()

