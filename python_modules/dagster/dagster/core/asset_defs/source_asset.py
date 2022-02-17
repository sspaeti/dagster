from typing import Any, NamedTuple, Optional

from dagster.core.definitions.events import AssetKey


class SourceAsset(NamedTuple):
    """A SourceAsset represents an asset that is not generated by any Dagster op in the repository
    that it's referenced from.

    Attributes:
        key (AssetKey): The key of the asset.
        metadata (Optional[Any]): Metadata associated with the asset.
        io_manager_key (str): The key for the IOManager that will be used to load the contents of
            the asset when it's used as an input to other assets inside a job.
        description (Optional[str]): The description of the asset.
    """

    key: AssetKey
    metadata: Optional[Any] = None
    io_manager_key: str = "io_manager"
    description: Optional[str] = None