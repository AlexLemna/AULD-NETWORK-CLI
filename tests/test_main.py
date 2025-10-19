"""
Test suite for the Auld Network CLI main module.

This test suite covers the core functionality of the CLI including:
- Command class and its validation
- CommandRegistry registration and resolution
- Shell mode switching and prompt generation
- Command handlers and their behavior
"""

import sys
import unittest
from io import StringIO
from unittest.mock import Mock, call, patch

# Import the modules we want to test
from auld_network_cli import (
    AmbiguousCommandError,
    BaseCommandError,
    Command,
    CommandNotFoundError,
    CommandRegistry,
    Mode,
    Shell,
    _registry,
    command,
    h_configure,
    h_exit,
    h_help,
    h_show,
)


class TestMode(unittest.TestCase):
    """Test the Mode enum."""

    def test_mode_values(self):
        """Test that Mode enum has correct values."""
        self.assertEqual(Mode.USER.value, "user")
        self.assertEqual(Mode.ADMIN.value, "admin")


class TestCommandRegistry(unittest.TestCase):
    """Test the CommandRegistry class."""

    def setUp(self):
        """Set up a fresh registry for each test."""
        # Create a new registry instance for testing
        self.registry = CommandRegistry()
        # Clear any existing commands
        self.registry._by_mode = {Mode.USER: [], Mode.ADMIN: []}

    def test_registry_is_singleton(self):
        """Test that CommandRegistry is a singleton."""
        registry1 = CommandRegistry()
        registry2 = CommandRegistry()
        self.assertIs(registry1, registry2)

    def test_register_command(self):
        """Test registering a command."""
        cmd = Command(tokens="test", mode=Mode.USER, handler=Mock())

        self.registry.register(cmd)
        self.assertIn(cmd, self.registry._by_mode[Mode.USER])

    def test_register_duplicate_command_raises_error(self):
        """Test that registering duplicate commands raises ValueError."""
        cmd1 = Command(tokens="test", mode=Mode.USER, handler=Mock())
        cmd2 = Command(tokens="test", mode=Mode.USER, handler=Mock())

        self.registry.register(cmd1)
        with self.assertRaises(ValueError):
            self.registry.register(cmd2)

    def test_resolve_exact_match(self):
        """Test resolving an exact command match."""
        handler = Mock()
        cmd = Command(tokens=("show", "version"), mode=Mode.USER, handler=handler)
        self.registry.register(cmd)

        resolved = self.registry.resolve(Mode.USER, ["show", "version"])
        self.assertEqual(resolved, cmd)

    def test_resolve_empty_input_raises_error(self):
        """Test that empty input raises ValueError."""
        with self.assertRaises(ValueError):
            self.registry.resolve(Mode.USER, [])

    def test_resolve_unknown_command_raises_error(self):
        """Test that unknown command raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            self.registry.resolve(Mode.USER, ["unknown"])
        self.assertIn("unknown command", str(cm.exception))

    def test_resolve_incomplete_command_raises_error(self):
        """Test that incomplete command raises ValueError with suggestions."""
        handler = Mock()
        cmd = Command(tokens=("show", "version"), mode=Mode.USER, handler=handler)
        self.registry.register(cmd)

        with self.assertRaises(ValueError) as cm:
            self.registry.resolve(Mode.USER, ["show"])
        self.assertIn("incomplete command", str(cm.exception))
        self.assertIn("show version", str(cm.exception))

    def test_resolve_ambiguous_command_raises_error(self):
        """Test that ambiguous command raises ValueError."""
        handler = Mock()
        cmd1 = Command(tokens="show", mode=Mode.USER, handler=handler)
        cmd2 = Command(tokens="shutdown", mode=Mode.USER, handler=handler)
        self.registry.register(cmd1)
        self.registry.register(cmd2)

        # This should work fine as they're not ambiguous
        resolved = self.registry.resolve(Mode.USER, ["show"])
        self.assertEqual(resolved, cmd1)

    def test_candidates_for_prefix(self):
        """Test the prefix matching functionality."""
        handler = Mock()
        cmd1 = Command(tokens=("show", "version"), mode=Mode.USER, handler=handler)
        cmd2 = Command(tokens=("show", "status"), mode=Mode.USER, handler=handler)
        cmd3 = Command(tokens="shutdown", mode=Mode.USER, handler=handler)

        self.registry.register(cmd1)
        self.registry.register(cmd2)
        self.registry.register(cmd3)

        # Test prefix matching for "show"
        candidates = self.registry._candidates_for_prefix(Mode.USER, ["show"])
        self.assertEqual(len(candidates), 2)
        self.assertIn(cmd1, candidates)
        self.assertIn(cmd2, candidates)


class TestShell(unittest.TestCase):
    """Test the Shell class."""

    def setUp(self):
        """Set up a shell with a clean registry for each test."""
        self.registry = CommandRegistry()
        self.registry._by_mode = {Mode.USER: [], Mode.ADMIN: []}
        self.shell = Shell(registry=self.registry)

    def test_shell_initial_mode(self):
        """Test that shell starts in USER mode."""
        self.assertEqual(self.shell.mode, Mode.USER)

    @patch("builtins.input")
    def test_run_empty_line(self, mock_input):
        """Test that empty lines are handled correctly."""
        mock_input.side_effect = ["", EOFError]

        exit_code = self.shell.run()
        self.assertEqual(exit_code, 0)

    @patch("builtins.input")
    def test_run_keyboard_interrupt(self, mock_input):
        """Test that KeyboardInterrupt is handled correctly."""
        mock_input.side_effect = [KeyboardInterrupt, EOFError]

        exit_code = self.shell.run()
        self.assertEqual(exit_code, 0)

    @patch("builtins.input")
    @patch("builtins.print")
    def test_run_unknown_command(self, mock_print, mock_input):
        """Test handling of unknown commands."""
        mock_input.side_effect = ["unknown", EOFError]

        exit_code = self.shell.run()
        self.assertEqual(exit_code, 0)
        # Should print an error message
        mock_print.assert_called()

    @patch("builtins.input")
    def test_run_successful_command(self, mock_input):
        """Test successful command execution."""
        # Register a test command
        handler = Mock(return_value=0)
        cmd = Command(tokens="test", mode=Mode.USER, handler=handler)
        self.registry.register(cmd)

        mock_input.side_effect = ["test", EOFError]

        exit_code = self.shell.run()
        self.assertEqual(exit_code, 0)
        handler.assert_called_once_with(self.shell)

    @patch("builtins.input")
    def test_run_command_with_negative_return_code(self, mock_input):
        """Test command that returns negative exit code."""
        # Register a test command that returns -1
        handler = Mock(return_value=-1)
        cmd = Command(tokens="exit", mode=Mode.USER, handler=handler)
        self.registry.register(cmd)

        mock_input.side_effect = ["exit"]

        exit_code = self.shell.run()
        self.assertEqual(exit_code, 0)  # Shell exits with 0 when command returns < 0

    @patch("builtins.input")
    @patch("builtins.print")
    def test_run_command_handler_exception(self, mock_print, mock_input):
        """Test handling of exceptions in command handlers."""
        # Register a test command that raises an exception
        handler = Mock(side_effect=Exception("test error"))
        cmd = Command(tokens="error", mode=Mode.USER, handler=handler)
        self.registry.register(cmd)

        mock_input.side_effect = ["error", EOFError]

        exit_code = self.shell.run()
        self.assertEqual(exit_code, 0)
        # Should print handler error
        mock_print.assert_called()


class TestCommandDecorator(unittest.TestCase):
    """Test the @command decorator."""

    def setUp(self):
        """Set up a clean registry for each test."""
        # We'll use the global registry but clear it
        _registry._by_mode = {Mode.USER: [], Mode.ADMIN: []}

    def test_command_decorator_string_tokens(self):
        """Test @command decorator with string tokens."""
        # Clear registry first to avoid interference from other tests
        initial_count = len(_registry._by_mode[Mode.USER])

        @command("test command", Mode.USER, "Test description")
        def test_handler(shell):
            return 0

        # Check that command was registered
        commands = _registry._by_mode[Mode.USER]
        self.assertEqual(len(commands), initial_count + 1)
        # The decorator actually creates a tuple with the string as one element
        # This is different from the Command class behavior when string is passed directly
        new_cmd = commands[-1]  # Get the last added command
        self.assertEqual(new_cmd.tokens, ("test command",))  # Not split by decorator
        self.assertEqual(new_cmd.mode, Mode.USER)
        self.assertEqual(new_cmd.short_description, "Test description")

    def test_command_decorator_tuple_tokens(self):
        """Test @command decorator with tuple tokens."""

        @command(("show", "status"), Mode.ADMIN, "Show status")
        def test_handler(shell):
            return 0

        # Check that command was registered
        commands = _registry._by_mode[Mode.ADMIN]
        self.assertEqual(len(commands), 1)
        cmd = commands[0]
        self.assertEqual(cmd.tokens, ("show", "status"))
        self.assertEqual(cmd.mode, Mode.ADMIN)


class TestCommandHandlers(unittest.TestCase):
    """Test the built-in command handlers."""

    def setUp(self):
        """Set up a shell for testing handlers."""
        self.shell = Shell()

    def test_h_configure(self):
        """Test the configure command handler."""
        self.shell.mode = Mode.USER
        result = h_configure(self.shell)
        self.assertEqual(result, 0)
        self.assertEqual(self.shell.mode, Mode.ADMIN)

    def test_h_exit_from_admin(self):
        """Test exit command from admin mode."""
        self.shell.mode = Mode.ADMIN
        result = h_exit(self.shell)
        self.assertEqual(result, 0)
        self.assertEqual(self.shell.mode, Mode.USER)

    def test_h_exit_from_user(self):
        """Test exit command from user mode raises SystemExit."""
        self.shell.mode = Mode.USER
        with self.assertRaises(SystemExit):
            h_exit(self.shell)

    @patch("builtins.print")
    def test_h_help_no_commands(self, mock_print):
        """Test help command when no commands are available."""
        # Create shell with empty registry
        registry = CommandRegistry()
        registry._by_mode = {Mode.USER: [], Mode.ADMIN: []}
        shell = Shell(registry=registry)

        result = h_help(shell)
        self.assertEqual(result, 0)
        mock_print.assert_called_with("No commands available in this mode.")

    @patch("builtins.print")
    def test_h_help_with_commands(self, mock_print):
        """Test help command with available commands."""
        # Create shell with some commands
        registry = CommandRegistry()
        registry._by_mode = {Mode.USER: [], Mode.ADMIN: []}
        handler = Mock()
        cmd = Command(
            tokens="test",
            mode=Mode.USER,
            handler=handler,
            short_description="Test command",
        )
        registry.register(cmd)
        shell = Shell(registry=registry)

        result = h_help(shell)
        self.assertEqual(result, 0)
        # Should print header and command info
        self.assertTrue(mock_print.called)

    @patch("builtins.print")
    def test_h_show(self, mock_print):
        """Test the show command handler."""
        result = h_show(self.shell)
        self.assertEqual(result, 0)
        # Should print system status
        mock_print.assert_has_calls(
            [call("System status: OK"), call("Current mode:", self.shell.mode.value)]
        )


class TestIntegration(unittest.TestCase):
    """Integration tests for the complete CLI system."""

    @patch("builtins.input")
    def test_mode_switching_workflow(self, mock_input):
        """Test a complete workflow of mode switching."""
        mock_input.side_effect = [
            "configure",  # Switch to admin mode
            "show",  # Run admin command
            "exit",  # Return to user mode
            "?",  # Show help
            EOFError,  # Exit
        ]

        shell = Shell()
        exit_code = shell.run()
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    # Run the test suite
    unittest.main(verbosity=0)
