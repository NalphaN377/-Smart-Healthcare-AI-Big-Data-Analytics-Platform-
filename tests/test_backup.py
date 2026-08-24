import pytest

from app.data_layer import backup


def test_restore_target_rejects_business_database():
    with pytest.raises(ValueError, match="禁止覆盖"):
        backup.validate_target_database("yiliaoBigData")


@pytest.mark.parametrize("value", ["bad-name", "1bad", "bad name", "x" * 64])
def test_restore_target_rejects_unsafe_names(value):
    with pytest.raises(ValueError):
        backup.validate_target_database(value)


def test_default_backup_path_is_scoped_and_timestamped():
    path = backup.default_backup_path()
    assert path.suffix == ".bak"
    assert path.name.startswith("yiliaoBigData_full_")
    assert backup.BACKUP_DIR.resolve() in path.parents
