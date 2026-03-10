from vito_tester.log_reader import VITOLogReader


class _FakeStdout:
    def __init__(self, text):
        self._text = text

    def read(self):
        return self._text.encode("utf-8")


class _FakeSSH:
    def __init__(self):
        self.connected = False
        self.commands = []

    def connect(self, **kwargs):
        self.connected = True

    def exec_command(self, command):
        self.commands.append(command)
        if "grep -c" in command:
            return None, _FakeStdout("3"), None
        return None, _FakeStdout("log output"), None

    def close(self):
        self.connected = False


def test_log_reader_reads_tail_and_count():
    reader = VITOLogReader(
        ssh_host="host",
        ssh_user="user",
        ssh_key_path="/tmp/key",
        log_path="/tmp/vito.log",
        ssh_client_factory=_FakeSSH,
    )
    assert reader.connect() is True
    assert "log output" in reader.tail_log(10)
    assert reader.get_error_count() == 3
    reader.close()
