import os
from wo.core.fileutils import WOFileUtils

class Dummy:
    class App:
        class Log:
            def debug(self, *args, **kwargs):
                pass
            def error(self, *args, **kwargs):
                pass
            def info(self, *args, **kwargs):
                pass
            def warning(self, *args, **kwargs):
                pass
        log = Log()
    app = App()

def test_copyfiles_overwrite(tmp_path):
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    src.mkdir()
    dest.mkdir()
    (src / "index.php").write_text("hello")
    (dest / "old.txt").write_text("old")
    # ensure destination initially has a different file
    WOFileUtils.copyfiles(Dummy(), str(src), str(dest), overwrite=True)
    assert (dest / "index.php").read_text() == "hello"
    assert not (dest / "old.txt").exists()
