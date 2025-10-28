"""
Comprehensive test suite for netmiko-only functionality in netpalm.
This test suite covers all netmiko driver capabilities to ensure
functionality is preserved after removing other drivers.
"""

from unittest.mock import Mock, MagicMock, patch
import pytest
from pytest_mock import MockerFixture

from netstacker.exceptions import NetstackerMetaProcessedException
from netstacker.backend.plugins.drivers.netmiko.netmiko_drvr import netmko
from netstacker.backend.core.calls.getconfig.exec_command import exec_command
from netstacker.backend.core.calls.setconfig.exec_config import exec_config


NETMIKO_TEST_DEVICE_ARGS = {
    "device_type": "cisco_ios",
    "host": "192.168.1.1",
    "username": "admin",
    "password": "admin",
    "port": 22
}


@pytest.fixture()
def rq_job(mocker: MockerFixture) -> MockerFixture:
    """Mock RQ job for tracking errors."""
    mocked_get_current_job = mocker.patch(
        'netstacker.backend.core.utilities.rediz_meta.get_current_job'
    )
    mocked_job = Mock()
    mocked_job.meta = {"errors": []}
    mocked_get_current_job.return_value = mocked_job


@pytest.fixture()
def netmiko_mock_session(mocker: MockerFixture) -> Mock:
    """Create a comprehensive mocked netmiko session."""
    mocked_CH = mocker.patch(
        'netstacker.backend.plugins.drivers.netmiko.netmiko_drvr.ConnectHandler',
        autospec=True
    )

    mocked_session = Mock()
    mocked_CH.return_value = mocked_session
    mocked_CH.session = mocked_session

    # Mock standard methods
    mocked_session.send_command.return_value = "command output"
    mocked_session.send_config_set.return_value = "config output"
    mocked_session.commit.return_value = "committed"
    mocked_session.save_config.return_value = "config saved"
    mocked_session.disconnect.return_value = None
    mocked_session.enable.return_value = None
    mocked_session.exit_enable_mode.return_value = None
    mocked_session.set_base_prompt.return_value = None

    return mocked_CH


class TestNetmikoDriverBasics:
    """Test basic netmiko driver functionality."""

    def test_driver_initialization(self):
        """Test driver initialization with various kwargs."""
        driver = netmko(
            args={"use_textfsm": True},
            connection_args=NETMIKO_TEST_DEVICE_ARGS
        )
        assert driver.driver_name == "netmiko"
        assert driver.connection_args == NETMIKO_TEST_DEVICE_ARGS
        assert driver.kwarg == {"use_textfsm": True}

    def test_driver_initialization_with_commit_label(self):
        """Test driver initialization with IOSXR commit label."""
        driver = netmko(
            args={"commit_label": "netstacker_change_123"},
            connection_args=NETMIKO_TEST_DEVICE_ARGS
        )
        assert driver.commit_label == "netstacker_change_123"
        assert "commit_label" not in driver.kwarg

    def test_driver_initialization_with_enable_mode(self):
        """Test driver initialization with enable_mode flag."""
        driver = netmko(
            connection_args=NETMIKO_TEST_DEVICE_ARGS,
            enable_mode=True
        )
        assert driver.enable_mode is True

    def test_connect(self, netmiko_mock_session: Mock):
        """Test connection establishment."""
        driver = netmko(connection_args=NETMIKO_TEST_DEVICE_ARGS)
        session = driver.connect()

        netmiko_mock_session.assert_called_once_with(**NETMIKO_TEST_DEVICE_ARGS)
        assert session is not None

    def test_logout(self, netmiko_mock_session: Mock):
        """Test session disconnection."""
        driver = netmko(connection_args=NETMIKO_TEST_DEVICE_ARGS)
        session = driver.connect()
        result = driver.logout(session)

        session.disconnect.assert_called_once()


class TestNetmikoSendCommand:
    """Test netmiko sendcommand functionality."""

    def test_send_single_command(self, netmiko_mock_session: Mock):
        """Test sending a single command."""
        driver = netmko(connection_args=NETMIKO_TEST_DEVICE_ARGS)
        session = driver.connect()
        session.send_command.return_value = "hostname router1"

        result = driver.sendcommand(session, ["show run | i hostname"])

        session.send_command.assert_called_once_with("show run | i hostname")
        assert "show run | i hostname" in result
        assert isinstance(result["show run | i hostname"], list)

    def test_send_multiple_commands(self, netmiko_mock_session: Mock):
        """Test sending multiple commands."""
        driver = netmko(connection_args=NETMIKO_TEST_DEVICE_ARGS)
        session = driver.connect()

        commands = ["show version", "show ip int brief", "show run"]
        session.send_command.side_effect = ["version output", "interface output", "running config"]

        result = driver.sendcommand(session, commands)

        assert len(result) == 3
        assert "show version" in result
        assert "show ip int brief" in result
        assert "show run" in result

    def test_send_command_with_textfsm(self, netmiko_mock_session: Mock):
        """Test sending command with TextFSM parsing."""
        driver = netmko(
            connection_args=NETMIKO_TEST_DEVICE_ARGS,
            args={"use_textfsm": True}
        )
        session = driver.connect()
        session.send_command.return_value = [{"interface": "Gi0/0", "status": "up"}]

        result = driver.sendcommand(session, ["show ip int brief"])

        session.send_command.assert_called_once_with(
            "show ip int brief",
            use_textfsm=True
        )
        assert result["show ip int brief"] == [{"interface": "Gi0/0", "status": "up"}]

    def test_send_command_with_ttp_template(self, netmiko_mock_session: Mock, mocker: MockerFixture):
        """Test sending command with TTP template."""
        mocker.patch('netstacker.backend.core.confload.confload.config.ttp_templates',
                     'netstacker/backend/plugins/extensibles/ttp_templates/')

        driver = netmko(
            connection_args=NETMIKO_TEST_DEVICE_ARGS,
            args={"ttp_template": "cisco_ios_show_version"}
        )
        session = driver.connect()
        session.send_command.return_value = {"version": "15.0"}

        result = driver.sendcommand(session, ["show version"])

        # Verify TTP template path was normalized
        call_args = session.send_command.call_args
        assert "ttp_template" in call_args[1]
        assert call_args[1]["ttp_template"].endswith(".ttp")

    def test_send_command_with_genie(self, netmiko_mock_session: Mock):
        """Test sending command with Genie parsing."""
        driver = netmko(
            connection_args=NETMIKO_TEST_DEVICE_ARGS,
            args={"use_genie": True}
        )
        session = driver.connect()
        session.send_command.return_value = {"interfaces": {}}

        result = driver.sendcommand(session, ["show interfaces"])

        session.send_command.assert_called_once_with(
            "show interfaces",
            use_genie=True
        )

    def test_send_command_with_enable_mode(self, netmiko_mock_session: Mock):
        """Test sending command with enable mode."""
        driver = netmko(
            connection_args=NETMIKO_TEST_DEVICE_ARGS,
            enable_mode=True
        )
        session = driver.connect()
        session.send_command.return_value = "running config"

        result = driver.sendcommand(session, ["show run"])

        session.enable.assert_called_once()
        session.exit_enable_mode.assert_called_once()


class TestNetmikoConfig:
    """Test netmiko config functionality."""

    def test_config_single_command(self, netmiko_mock_session: Mock, rq_job):
        """Test applying a single configuration command."""
        driver = netmko(connection_args=NETMIKO_TEST_DEVICE_ARGS)
        session = driver.connect()
        session.send_config_set.return_value = "config applied"

        result = driver.config(session, "hostname router1")

        session.send_config_set.assert_called_once_with(["hostname router1"])
        session.commit.assert_called_once()
        assert "changes" in result

    def test_config_multiple_commands(self, netmiko_mock_session: Mock, rq_job):
        """Test applying multiple configuration commands."""
        driver = netmko(connection_args=NETMIKO_TEST_DEVICE_ARGS)
        session = driver.connect()
        session.send_config_set.return_value = "config applied"

        config_commands = ["hostname router1", "no ip domain lookup"]
        result = driver.config(session, config_commands)

        session.send_config_set.assert_called_once_with(config_commands)
        assert "changes" in result

    def test_config_multiline_string(self, netmiko_mock_session: Mock, rq_job):
        """Test applying multiline configuration string."""
        driver = netmko(connection_args=NETMIKO_TEST_DEVICE_ARGS)
        session = driver.connect()
        session.send_config_set.return_value = "config applied"

        config = "hostname router1\nno ip domain lookup\nip domain name example.com"
        result = driver.config(session, config)

        expected_commands = config.split('\n')
        session.send_config_set.assert_called_once_with(expected_commands)

    def test_config_dry_run(self, netmiko_mock_session: Mock, rq_job):
        """Test dry run configuration (no commit)."""
        driver = netmko(connection_args=NETMIKO_TEST_DEVICE_ARGS)
        session = driver.connect()
        session.send_config_set.return_value = "config applied"

        result = driver.config(session, "hostname router1", dry_run=True)

        session.send_config_set.assert_called_once()
        session.commit.assert_not_called()
        session.save_config.assert_not_called()

    def test_config_with_enable_mode(self, netmiko_mock_session: Mock, rq_job):
        """Test configuration with enable mode."""
        driver = netmko(connection_args=NETMIKO_TEST_DEVICE_ARGS)
        session = driver.connect()
        session.send_config_set.return_value = "config applied"

        result = driver.config(session, "hostname router1", enter_enable=True)

        session.enable.assert_called_once()

    def test_config_with_commit_label(self, netmiko_mock_session: Mock, rq_job):
        """Test configuration with IOSXR commit label."""
        driver = netmko(
            connection_args=NETMIKO_TEST_DEVICE_ARGS,
            args={"commit_label": "netstacker_123"}
        )
        session = driver.connect()
        session.send_config_set.return_value = "config applied"
        session.commit.return_value = "committed with label"

        result = driver.config(session, "hostname router1")

        session.commit.assert_called_once_with(label="netstacker_123")

    def test_config_fallback_to_save(self, netmiko_mock_session: Mock, rq_job):
        """Test configuration fallback to save_config when commit not available."""
        driver = netmko(connection_args=NETMIKO_TEST_DEVICE_ARGS)
        session = driver.connect()
        session.send_config_set.return_value = "config applied"
        session.commit.side_effect = NotImplementedError()
        session.save_config.return_value = "config saved"

        result = driver.config(session, "hostname router1")

        session.commit.assert_called_once()
        session.save_config.assert_called_once()
        assert "config saved" in result["changes"]


class TestNetmikoExecCommand:
    """Test exec_command integration with netmiko driver."""

    def test_exec_command_basic(self, netmiko_mock_session: Mock):
        """Test basic command execution through exec_command."""
        session = netmiko_mock_session.return_value
        session.send_command.return_value = "hostname router1"

        result = exec_command(
            library="netmiko",
            command="show run | i hostname",
            connection_args=NETMIKO_TEST_DEVICE_ARGS
        )

        netmiko_mock_session.assert_called_once_with(**NETMIKO_TEST_DEVICE_ARGS)
        session.disconnect.assert_called_once()
        assert "show run | i hostname" in result

    def test_exec_command_multiple(self, netmiko_mock_session: Mock):
        """Test multiple command execution through exec_command."""
        session = netmiko_mock_session.return_value
        session.send_command.side_effect = ["output1", "output2"]

        result = exec_command(
            library="netmiko",
            command=["show version", "show ip int brief"],
            connection_args=NETMIKO_TEST_DEVICE_ARGS
        )

        assert len(result) == 2

    def test_exec_command_with_textfsm(self, netmiko_mock_session: Mock):
        """Test command execution with TextFSM parser."""
        session = netmiko_mock_session.return_value
        session.send_command.return_value = [{"interface": "Gi0/0"}]

        result = exec_command(
            library="netmiko",
            command="show ip int brief",
            connection_args=NETMIKO_TEST_DEVICE_ARGS,
            args={"use_textfsm": True}
        )

        assert result["show ip int brief"] == [{"interface": "Gi0/0"}]

    def test_exec_command_post_checks_success(self, netmiko_mock_session: Mock, rq_job):
        """Test command execution with successful post-checks."""
        session = netmiko_mock_session.return_value
        session.send_command.side_effect = ["hostname router1", "hostname router1"]

        post_check = {
            "get_config_args": {"command": "show run | i hostname"},
            "match_str": ["router1"],
            "match_type": "include"
        }

        result = exec_command(
            library="netmiko",
            command="show run | i hostname",
            connection_args=NETMIKO_TEST_DEVICE_ARGS,
            post_checks=[post_check]
        )

        assert result is not None

    def test_exec_command_post_checks_failure(self, netmiko_mock_session: Mock, rq_job):
        """Test command execution with failing post-checks."""
        session = netmiko_mock_session.return_value
        session.send_command.side_effect = ["hostname router1", "hostname router1"]

        post_check = {
            "get_config_args": {"command": "show run | i hostname"},
            "match_str": ["router1"],
            "match_type": "exclude"  # This will fail since router1 is in output
        }

        with pytest.raises(NetstackerMetaProcessedException):
            exec_command(
                library="netmiko",
                command="show run | i hostname",
                connection_args=NETMIKO_TEST_DEVICE_ARGS,
                post_checks=[post_check]
            )


class TestNetmikoExecConfig:
    """Test exec_config integration with netmiko driver."""

    def test_exec_config_basic(self, netmiko_mock_session: Mock, rq_job):
        """Test basic config execution through exec_config."""
        session = netmiko_mock_session.return_value
        session.send_config_set.return_value = "hostname router1"

        result = exec_config(
            library="netmiko",
            config=["hostname router1"],
            connection_args=NETMIKO_TEST_DEVICE_ARGS
        )

        netmiko_mock_session.assert_called_once_with(**NETMIKO_TEST_DEVICE_ARGS)
        session.send_config_set.assert_called_once()
        assert "changes" in result

    def test_exec_config_with_j2_template(self, netmiko_mock_session: Mock, rq_job, mocker: MockerFixture):
        """Test config execution with Jinja2 template."""
        # Mock Jinja2 rendering
        mocker.patch(
            'netstacker.backend.core.utilities.jinja2.j2.render_j2template',
            return_value=["hostname router1", "no ip domain lookup"]
        )

        session = netmiko_mock_session.return_value
        session.send_config_set.return_value = "config applied"

        result = exec_config(
            library="netmiko",
            j2config={
                "template": "test_template",
                "args": {"hostname": "router1"}
            },
            connection_args=NETMIKO_TEST_DEVICE_ARGS
        )

        session.send_config_set.assert_called_once()

    def test_exec_config_pre_checks_success(self, netmiko_mock_session: Mock, rq_job):
        """Test config execution with successful pre-checks."""
        session = netmiko_mock_session.return_value
        session.send_command.return_value = "hostname router1"
        session.send_config_set.return_value = "config applied"

        pre_check = {
            "get_config_args": {"command": "show run | i hostname"},
            "match_str": ["router1"],
            "match_type": "include"
        }

        result = exec_config(
            library="netmiko",
            config=["hostname router2"],
            connection_args=NETMIKO_TEST_DEVICE_ARGS,
            pre_checks=[pre_check]
        )

        assert "changes" in result

    def test_exec_config_pre_checks_failure(self, netmiko_mock_session: Mock, rq_job):
        """Test config execution with failing pre-checks."""
        session = netmiko_mock_session.return_value
        session.send_command.return_value = "hostname router1"

        pre_check = {
            "get_config_args": {"command": "show run | i hostname"},
            "match_str": ["router2"],  # This will fail
            "match_type": "include"
        }

        with pytest.raises(NetstackerMetaProcessedException):
            exec_config(
                library="netmiko",
                config=["hostname router2"],
                connection_args=NETMIKO_TEST_DEVICE_ARGS,
                pre_checks=[pre_check]
            )


class TestNetmikoDeviceSupport:
    """Test netmiko support for various device types."""

    @pytest.mark.parametrize("device_type", [
        "cisco_ios",
        "cisco_xe",
        "cisco_xr",
        "cisco_nxos",
        "arista_eos",
        "juniper_junos",
        "hp_comware",
        "dell_os10",
        "paloalto_panos",
    ])
    def test_device_type_support(self, device_type, netmiko_mock_session: Mock):
        """Test that various device types can be initialized."""
        connection_args = NETMIKO_TEST_DEVICE_ARGS.copy()
        connection_args["device_type"] = device_type

        driver = netmko(connection_args=connection_args)
        session = driver.connect()

        netmiko_mock_session.assert_called_once()
        assert netmiko_mock_session.call_args[1]["device_type"] == device_type


class TestNetmikoErrorHandling:
    """Test netmiko error handling."""

    def test_connection_error_handling(self, netmiko_mock_session: Mock, rq_job):
        """Test error handling during connection."""
        netmiko_mock_session.side_effect = Exception("Connection refused")

        driver = netmko(connection_args=NETMIKO_TEST_DEVICE_ARGS)
        result = driver.connect()

        # Error should be written to meta, but not raise
        assert result is None

    def test_sendcommand_error_handling(self, netmiko_mock_session: Mock, rq_job):
        """Test error handling during sendcommand."""
        session = netmiko_mock_session.return_value
        session.send_command.side_effect = Exception("Command failed")

        driver = netmko(connection_args=NETMIKO_TEST_DEVICE_ARGS)
        session_obj = driver.connect()
        result = driver.sendcommand(session_obj, ["show version"])

        assert result is None

    def test_config_error_handling(self, netmiko_mock_session: Mock, rq_job):
        """Test error handling during config."""
        session = netmiko_mock_session.return_value
        session.send_config_set.side_effect = Exception("Config failed")

        driver = netmko(connection_args=NETMIKO_TEST_DEVICE_ARGS)
        session_obj = driver.connect()
        result = driver.config(session_obj, "hostname router1")

        assert result is None


class TestNetmikoEdgeCases:
    """Test netmiko edge cases and special scenarios."""

    def test_empty_command_list(self, netmiko_mock_session: Mock):
        """Test handling of empty command list."""
        driver = netmko(connection_args=NETMIKO_TEST_DEVICE_ARGS)
        session = driver.connect()

        result = driver.sendcommand(session, [])

        assert result == {}

    def test_empty_response_filtering(self, netmiko_mock_session: Mock):
        """Test that empty responses are not included in results."""
        driver = netmko(connection_args=NETMIKO_TEST_DEVICE_ARGS)
        session = driver.connect()
        session.send_command.return_value = ""

        result = driver.sendcommand(session, ["show version"])

        # Empty responses should not be in result dict
        assert "show version" not in result

    def test_config_with_empty_string(self, netmiko_mock_session: Mock, rq_job):
        """Test configuration with empty string."""
        driver = netmko(connection_args=NETMIKO_TEST_DEVICE_ARGS)
        session = driver.connect()
        session.send_config_set.return_value = ""

        result = driver.config(session, "")

        session.send_config_set.assert_called_once_with([""])

    def test_kwargs_without_args(self):
        """Test driver initialization without args parameter."""
        driver = netmko(connection_args=NETMIKO_TEST_DEVICE_ARGS)

        assert driver.kwarg is False
        assert driver.commit_label is None
