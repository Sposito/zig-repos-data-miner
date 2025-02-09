import subprocess
from unittest.mock import patch, mock_open
from scripts.regenerate_prompt import get_file_content_with_header, copy_to_clipboard, execute

def test_get_file_content_with_header():
    mock_data = "print('Hello, world!')"
    filepath = "scripts/regenerate_prompt.py"

    with patch("builtins.open", mock_open(read_data=mock_data)):
        content = get_file_content_with_header(filepath)

    expected_content = f"--- regenerate_prompt.py ---\n{mock_data}\n"
    assert content == expected_content

def test_get_file_content_with_header_file_not_found():
    filepath = "scripts/nonexistent.py"

    with patch("builtins.open", side_effect=FileNotFoundError("File not found")):
        content = get_file_content_with_header(filepath)

    assert "Error reading" in content
    assert "File not found" in content

def test_copy_to_clipboard_mac():
    with patch("platform.system", return_value="Darwin"), \
            patch("subprocess.Popen") as mock_popen:
        mock_process = mock_popen.return_value
        mock_process.communicate.return_value = (None, None)

        assert copy_to_clipboard("test text") is True
        mock_popen.assert_called_with(["pbcopy"], stdin=subprocess.PIPE)

def test_copy_to_clipboard_linux():
    with patch("platform.system", return_value="Linux"), \
            patch("subprocess.Popen") as mock_popen:
        mock_process = mock_popen.return_value
        mock_process.communicate.return_value = (None, None)

        assert copy_to_clipboard("test text") is True
        mock_popen.assert_called_with(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)

def test_copy_to_clipboard_unsupported_os():
    with patch("platform.system", return_value="Windows"), \
            patch("builtins.print") as mock_print:
        assert copy_to_clipboard("test text") is False
        mock_print.assert_called_with("Clipboard copy is only supported on macOS and Linux.")

def test_copy_to_clipboard_failure():
    with patch("platform.system", return_value="Linux"), \
            patch("subprocess.Popen", side_effect=Exception("Clipboard error")), \
            patch("builtins.print") as mock_print:
        assert copy_to_clipboard("test text") is False
        mock_print.assert_called_with("Failed to copy to clipboard: Clipboard error")

@patch("os.path.exists", side_effect=lambda path: path in ["scripts/regenerate_prompt.py", "tests"])
@patch("os.path.isdir", side_effect=lambda path: path == "tests")
@patch("os.listdir", return_value=["test_script_regen_prompt.py"])
@patch("builtins.open", mock_open(read_data="print('test')"))
@patch("scripts.regenerate_prompt.copy_to_clipboard", return_value=True)
@patch("builtins.print")
def test_main(mock_print, mock_clipboard, mock_listdir, mock_isdir, mock_exists):
    with patch("os.path.realpath", return_value="/absolute/path/scripts/regenerate_prompt.py"), \
            patch("os.path.abspath", return_value="/absolute/path"), \
            patch("os.path.join", side_effect=lambda *args: "/".join(args)):
        execute()

        mock_clipboard.assert_called_once()
        mock_print.assert_any_call("Prompt successfully copied to clipboard.")
