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
    Shell,
    ShellMode,
    _registry,
    cmd_configure,
    cmd_exit,
    cmd_help,
    cmd_show,
    command,
)


class TestMode(unittest.TestCase):
    """Test the Mode enum."""

    def test_mode_values(self):
        """Test that Mode enum has correct values."""
        self.assertEqual(ShellMode.USER.value, "user")
        self.assertEqual(ShellMode.ADMIN.value, "admin")


class TestCommandRegistry(unittest.TestCase):
    """Test the CommandRegistry class."""

    def setUp(self):
        """Set up a fresh registry for each test."""
        # Create a new registry instance for testing
        self.registry = CommandRegistry()
        # Clear any existing commands
        self.registry._by_mode = {ShellMode.USER: [], ShellMode.ADMIN: []}

    def test_registry_singleton(self):
        """Test that CommandRegistry is a singleton."""
        registry1 = CommandRegistry()
        registry2 = CommandRegistry()
        self.assertIs(registry1, registry2)

    def test_register_command(self):
        """Test registering a command."""

        def dummy_handler(shell):
            return 0

        cmd = Command(
            tokens=("test",),
            mode=ShellMode.USER,
            handler=dummy_handler,
            short_description="Test command",
        )

        self.registry.register(cmd)
        self.assertIn(cmd, self.registry._by_mode[ShellMode.USER])

    def test_register_duplicate_command_raises_error(self):
        """Test that registering duplicate commands raises an error."""

        def dummy_handler(shell):
            return 0

        cmd1 = Command(
            tokens=("test",),
            mode=ShellMode.USER,
            handler=dummy_handler,
            short_description="Test command 1",
        )

        cmd2 = Command(
            tokens=("test",),
            mode=ShellMode.USER,
            handler=dummy_handler,
            short_description="Test command 2",
        )

        self.registry.register(cmd1)
        with self.assertRaises(ValueError):
            self.registry.register(cmd2)


class TestCommand(unittest.TestCase):
    """Test the Command class."""

    def test_command_creation_with_tuple(self):
        """Test creating a command with tuple tokens."""

        def dummy_handler(shell):
            return 0

        cmd = Command(
            tokens=("show", "version"),
            mode=ShellMode.USER,
            handler=dummy_handler,
            short_description="Show version",
        )

        self.assertEqual(cmd.tokens, ("show", "version"))
        self.assertEqual(cmd.mode, ShellMode.USER)
        self.assertEqual(cmd.short_description, "Show version")

    def test_command_creation_with_string(self):
        """Test creating a command with string tokens (gets converted to tuple)."""

        def dummy_handler(shell):
            return 0

        cmd = Command(
            tokens="show version",
            mode=ShellMode.USER,
            handler=dummy_handler,
            short_description="Show version",
        )

        self.assertEqual(cmd.tokens, ("show", "version"))

    def test_command_empty_tokens_raises_error(self):
        """Test that empty tokens raise a ValueError."""

        def dummy_handler(shell):
            return 0

        with self.assertRaises(ValueError):
            Command(
                tokens=(),
                mode=ShellMode.USER,
                handler=dummy_handler,
                short_description="Empty command",
            )

        with self.assertRaises(ValueError):
            Command(
                tokens="",
                mode=ShellMode.USER,
                handler=dummy_handler,
                short_description="Empty command",
            )


class TestShell(unittest.TestCase):
    """Test the Shell class."""

    def setUp(self):
        """Set up a fresh shell for each test."""
        # Create a new registry for testing
        self.registry = CommandRegistry()
        self.registry._by_mode = {ShellMode.USER: [], ShellMode.ADMIN: []}
        self.shell = Shell(registry=self.registry)

    def test_shell_initial_mode(self):
        """Test that shell starts in USER mode."""
        self.assertEqual(self.shell.mode, ShellMode.USER)

    def test_prompt_user_mode(self):
        """Test prompt generation for user mode."""
        self.shell.mode = ShellMode.USER
        self.assertEqual(self.shell.prompt(), "Auld CLI> ")

    def test_prompt_admin_mode(self):
        """Test prompt generation for admin mode."""
        self.shell.mode = ShellMode.ADMIN
        self.assertEqual(self.shell.prompt(), "Auld CLI# ")


class TestCommandDecorator(unittest.TestCase):
    """Test the @command decorator."""

    def setUp(self):
        """Set up a fresh registry for each test."""
        # We'll use the global registry but clear it
        _registry._by_mode = {ShellMode.USER: [], ShellMode.ADMIN: []}

    def test_command_decorator_registration(self):
        """Test that @command decorator registers commands."""
        initial_count = len(_registry._by_mode[ShellMode.USER])

        @command("test", ShellMode.USER, "Test command")
        def test_handler(shell):
            return 0

        # Should have one more command now
        self.assertEqual(len(_registry._by_mode[ShellMode.USER]), initial_count + 1)

        # Find our command
        test_commands = [
            cmd for cmd in _registry._by_mode[ShellMode.USER] if cmd.tokens == ("test",)
        ]
        self.assertEqual(len(test_commands), 1)
        self.assertEqual(test_commands[0].short_description, "Test command")


class TestCommandHandlers(unittest.TestCase):
    """Test the built-in command handlers."""

    def setUp(self):
        """Set up a shell for testing handlers."""
        self.registry = CommandRegistry()
        self.registry._by_mode = {ShellMode.USER: [], ShellMode.ADMIN: []}
        self.shell = Shell(registry=self.registry)

    def test_configure_handler(self):
        """Test the configure command handler."""
        self.shell.mode = ShellMode.USER
        result = cmd_configure(self.shell)
        self.assertEqual(result, 0)
        self.assertEqual(self.shell.mode, ShellMode.ADMIN)

    def test_exit_handler_from_admin(self):
        """Test exit handler from admin mode."""
        self.shell.mode = ShellMode.ADMIN
        result = cmd_exit(self.shell)
        self.assertEqual(result, 0)
        self.assertEqual(self.shell.mode, ShellMode.USER)

    def test_exit_handler_from_user(self):
        """Test exit handler from user mode."""
        self.shell.mode = ShellMode.USER
        with self.assertRaises(SystemExit):
            cmd_exit(self.shell)

    @patch("builtins.print")
    def test_help_handler_no_commands(self, mock_print):
        """Test help handler when no commands are available."""
        self.shell.mode = ShellMode.USER
        result = cmd_help(self.shell)
        self.assertEqual(result, 0)
        mock_print.assert_called_with("No commands available in this mode.")

    @patch("builtins.print")
    def test_help_handler_with_commands(self, mock_print):
        """Test help handler when commands are available."""

        def dummy_handler(shell):
            return 0

        cmd = Command(
            tokens=("test",),
            mode=ShellMode.USER,
            handler=dummy_handler,
            short_description="Test command",
        )
        self.registry.register(cmd)

        self.shell.mode = ShellMode.USER
        result = cmd_help(self.shell)

        self.assertEqual(result, 0)
        # Check that print was called with the expected output
        calls = mock_print.call_args_list
        self.assertTrue(
            any("Available commands in user mode:" in str(call) for call in calls)
        )
        self.assertTrue(
            any("test" in str(call) and "Test command" in str(call) for call in calls)
        )

    @patch("builtins.print")
    def test_show_handler(self, mock_print):
        """Test the show command handler."""
        self.shell.mode = ShellMode.ADMIN
        result = cmd_show(self.shell)
        self.assertEqual(result, 0)

        # Check that appropriate messages were printed
        calls = mock_print.call_args_list
        self.assertTrue(any("System status: OK" in str(call) for call in calls))
        self.assertTrue(any("Current mode: admin" in str(call) for call in calls))


class TestCommandResolution(unittest.TestCase):
    """Test command resolution in the registry."""

    def setUp(self):
        """Set up a registry with test commands."""
        self.registry = CommandRegistry()
        self.registry._by_mode = {ShellMode.USER: [], ShellMode.ADMIN: []}

        def dummy_handler(shell):
            return 0

        # Add some test commands
        self.registry.register(
            Command(
                tokens=("show",),
                mode=ShellMode.USER,
                handler=dummy_handler,
                short_description="Show command",
            )
        )

        self.registry.register(
            Command(
                tokens=("show", "version"),
                mode=ShellMode.USER,
                handler=dummy_handler,
                short_description="Show version",
            )
        )

        self.registry.register(
            Command(
                tokens=("configure",),
                mode=ShellMode.USER,
                handler=dummy_handler,
                short_description="Configure",
            )
        )

    def test_resolve_exact_match(self):
        """Test resolving exact command matches."""
        cmd = self.registry.resolve(ShellMode.USER, ["show"])
        self.assertEqual(cmd.tokens, ("show",))

    def test_resolve_multi_token_command(self):
        """Test resolving multi-token commands."""
        cmd = self.registry.resolve(ShellMode.USER, ["show", "version"])
        self.assertEqual(cmd.tokens, ("show", "version"))

    def test_resolve_unknown_command(self):
        """Test resolving unknown commands raises error."""
        with self.assertRaises(ValueError) as cm:
            self.registry.resolve(ShellMode.USER, ["unknown"])
        self.assertIn("unknown command", str(cm.exception))

    def test_resolve_incomplete_command(self):
        """Test resolving incomplete commands suggests completions."""
        with self.assertRaises(ValueError) as cm:
            self.registry.resolve(ShellMode.USER, ["sh"])
        self.assertIn("incomplete command", str(cm.exception))
        self.assertIn("show", str(cm.exception))

    def test_resolve_empty_input(self):
        """Test resolving empty input raises error."""
        with self.assertRaises(ValueError) as cm:
            self.registry.resolve(ShellMode.USER, [])
        self.assertIn("empty input", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
