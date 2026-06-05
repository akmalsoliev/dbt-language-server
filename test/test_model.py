from src.dbt_ls.model import discover_models, Model


def test_discover_models():
    models = discover_models("testdata")
    assert set(models) == {
        Model(
            name="my_first_dbt_model",
            path="testdata/project/models/example/my_first_dbt_model.sql",
        ),
        Model(
            name="my_second_dbt_model",
            path="testdata/project/models/example/my_second_dbt_model.sql",
        ),
    }
