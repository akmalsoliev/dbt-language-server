import pytest
from dbt_ls.profiles import (
    ProfileTarget,
    DuckDBTarget,
    MySQLTarget,
    Secret,
    DatabaseTarget,
    MSSQLTarget,
)


@pytest.mark.parametrize(
    "target_dict, expected",
    [
        pytest.param(
            {"type": "duckdb", "threads": 1, "path": "dev.duckdb"},
            DuckDBTarget(type="duckdb", threads=1, path="dev.duckdb"),
        ),
        pytest.param(
            {
                "type": "mysql",
                "threads": 4,
                "user": "root",
                "password": "passwd",
                "server": "127.0.0.1",
                "port": 1433,
                "schema": "dev",
            },
            MySQLTarget(
                type="mysql",
                threads=4,
                user="root",
                password=Secret("passwd"),
                server="127.0.0.1",
                port=1433,
                schema="dev",
            ),
        ),
        pytest.param(
            {
                "type": "postgres",
                "threads": 4,
                "user": "postgres",
                "password": "passwd",
                "host": "127.0.0.1",
                "port": 5432,
                "schema": "dev",
                "dbname": "mydb",
            },
            DatabaseTarget(
                type="postgres",
                threads=4,
                user="postgres",
                password=Secret("passwd"),
                host="127.0.0.1",
                port=5432,
                schema="dev",
                dbname="mydb",
            ),
        ),
        pytest.param(
            {
                "type": "sqlserver",
                "threads": 4,
                "user": "sa",
                "password": "root",
                "server": "127.0.0.1",
                "port": 1234,
                "schema": "dev",
                "database": "mydb",
                "driver": "{MSSQL DRIVER}",
                "encrypt": False,
            },
            MSSQLTarget(
                type="sqlserver",
                threads=4,
                user="sa",
                password=Secret("root"),
                server="127.0.0.1",
                port=1234,
                schema="dev",
                database="mydb",
                driver="{MSSQL DRIVER}",
                encrypt=False,
            ),
        ),
    ],
    ids=["duckdb", "mysql", "postgres", "sqlserver"],
)
def test_target_from_dict(target_dict, expected):
    assert ProfileTarget.from_dict(target_dict) == expected
