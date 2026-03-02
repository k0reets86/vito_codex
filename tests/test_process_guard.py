from pathlib import Path

from modules.process_guard import (
    list_vito_main_pids,
    read_pidfile,
    select_primary_pid,
    write_pidfile,
)


def test_pidfile_read_write(tmp_path):
    pf = tmp_path / "vito.pid"
    write_pidfile(str(pf), 12345)
    assert read_pidfile(str(pf)) == 12345


def test_select_primary_prefers_pidfile():
    pids = [300, 200, 100]
    assert select_primary_pid(pids, pidfile_pid=200) == 200
    assert select_primary_pid(pids, pidfile_pid=999) == 100


def test_list_vito_main_pids_from_fake_proc(tmp_path):
    proc = tmp_path / "proc"
    proc.mkdir()

    def mk(pid: int, cmdline: str):
        d = proc / str(pid)
        d.mkdir()
        (d / "cmdline").write_bytes(cmdline.encode("utf-8"))

    mk(101, "python3\0-u\0main.py\0")
    mk(202, "python3\0other.py\0")
    mk(303, "node\0main.py\0")
    mk(404, "python\0/home/vito/vito-agent/main.py\0")

    got = list_vito_main_pids(proc_root=str(proc))
    assert got == [101, 404]
