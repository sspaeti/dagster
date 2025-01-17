from typing import Mapping

import dagster._check as check
from dagster import InputContext, MetadataValue, OutputContext, TableColumn, TableSchema
from dagster._core.definitions.metadata import RawMetadataValue
from dagster._core.storage.db_io_manager import DbTypeHandler, TableSlice
from dagster_snowflake import build_snowflake_io_manager
from pyspark.sql import DataFrame, SparkSession

SNOWFLAKE_CONNECTOR = "net.snowflake.spark.snowflake"


def _get_snowflake_options(config, table_slice: TableSlice) -> Mapping[str, str]:
    check.invariant(
        config.get("warehouse", None) is not None,
        "Missing config: Warehouse is required when using PySpark with the Snowflake I/O manager.",
    )

    conf = {
        "sfURL": f"{config['account']}.snowflakecomputing.com",
        "sfUser": config["user"],
        "sfPassword": config["password"],
        "sfDatabase": config["database"],
        "sfSchema": table_slice.schema,
        "sfWarehouse": config["warehouse"],
        "dbtable": table_slice.table,
    }

    print("THIS IS THE CONF")
    print(conf)

    return conf


class SnowflakePySparkTypeHandler(DbTypeHandler[DataFrame]):
    """
    Plugin for the Snowflake I/O Manager that can store and load PySpark DataFrames as Snowflake tables.

    Examples:
        .. code-block:: python

            from dagster_snowflake import build_snowflake_io_manager
            from dagster_snowflake_pyspark import SnowflakePySparkTypeHandler
            from pyspark.sql import DataFrame
            from dagster import Definitions

            snowflake_io_manager = build_snowflake_io_manager([SnowflakePySparkTypeHandler()])

            @asset
            def my_asset() -> DataFrame:
                ...

            defs = Definitions(
                assets=[my_asset],
                resources={
                    "io_manager": snowflake_io_manager.configured(...)
                }
            )

            # OR

            @job(resource_defs={'io_manager': snowflake_io_manager})
            def my_job():
                ...

    """

    def handle_output(
        self, context: OutputContext, table_slice: TableSlice, obj: DataFrame
    ) -> Mapping[str, RawMetadataValue]:
        options = _get_snowflake_options(context.resource_config, table_slice)
        print("OPTIONS")
        print(options)

        with_uppercase_cols = obj.toDF(*[c.upper() for c in obj.columns])

        with_uppercase_cols.write.format(SNOWFLAKE_CONNECTOR).options(**options).mode(
            "append"
        ).save()

        return {
            "dataframe_columns": MetadataValue.table_schema(
                TableSchema(
                    columns=[
                        TableColumn(name=field.name, type=field.dataType.typeName())
                        for field in obj.schema.fields
                    ]
                )
            ),
        }

    def load_input(self, context: InputContext, table_slice: TableSlice) -> DataFrame:
        options = _get_snowflake_options(context.resource_config, table_slice)

        spark = SparkSession.builder.getOrCreate()
        df = spark.read.format(SNOWFLAKE_CONNECTOR).options(**options).load()

        return df.toDF(*[c.lower() for c in df.columns])

    @property
    def supported_types(self):
        return [DataFrame]


snowflake_pyspark_io_manager = build_snowflake_io_manager([SnowflakePySparkTypeHandler()])
snowflake_pyspark_io_manager.__doc__ = """
An IO manager definition that reads inputs from and writes PySpark DataFrames to Snowflake.

Returns:
    IOManagerDefinition

Examples:

    .. code-block:: python

        from dagster_snowflake_pyspark import snowflake_pyspark_io_manager
        from pyspark.sql import DataFrame
        from dagster import Definitions

        @asset(
            key_prefix=["my_schema"]  # will be used as the schema in snowflake
        )
        def my_table() -> DataFrame:  # the name of the asset will be the table name
            ...

        defs = Definitions(
            assets=[my_table],
            resources={
                "io_manager": snowflake_pyspark_io_manager.configured({
                    "database": "my_database",
                    "warehouse": "my_warehouse", # required for snowflake_pyspark_io_manager
                    "account" : {"env": "SNOWFLAKE_ACCOUNT"},
                    "password": {"env": "SNOWFLAKE_PASSWORD"},
                    ...
                })
            }
        )

    Note that the warehouse configuration value is required when using the snowflake_pyspark_io_manager

    If you do not provide a schema, Dagster will determine a schema based on the assets and ops using
    the IO Manager. For assets, the schema will be determined from the asset key.
    For ops, the schema can be specified by including a "schema" entry in output metadata. If "schema" is not provided
    via config or on the asset/op, "public" will be used for the schema.

    .. code-block:: python

        @op(
            out={"my_table": Out(metadata={"schema": "my_schema"})}
        )
        def make_my_table() -> DataFrame:
            # the returned value will be stored at my_schema.my_table
            ...

    To only use specific columns of a table as input to a downstream op or asset, add the metadata "columns" to the
    In or AssetIn.

    .. code-block:: python

        @asset(
            ins={"my_table": AssetIn("my_table", metadata={"columns": ["a"]})}
        )
        def my_table_a(my_table: DataFrame) -> DataFrame:
            # my_table will just contain the data from column "a"
            ...

"""
