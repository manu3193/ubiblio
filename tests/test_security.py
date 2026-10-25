import os

from ubiblio.security import archive_stays_inside, contained_file


def test_contained_file_accepts_a_plain_name(tmp_path):
    root = tmp_path / "export"
    root.mkdir()
    target = root / "daily.sql"
    target.write_text("ok", encoding="utf-8")
    assert contained_file(str(root), "daily.sql") == os.path.realpath(target)


def test_contained_file_rejects_a_name_with_a_directory():
    assert contained_file("export", "nested/daily.sql") is None
    assert contained_file("export", "..") is None


def test_archive_rejects_members_that_leave_the_destination(tmp_path):
    import zipfile
    archive_path = tmp_path / "files.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.txt", "no")
    assert archive_stays_inside(str(archive_path), str(tmp_path / "static")) is False
