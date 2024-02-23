from datetime import datetime
from datetime import timedelta as TimeDelta
from typing import Any, Optional

import msgspec
from flask import Flask
from itsdangerous import want_bytes
from ..defaults import Defaults
from ..base import ServerSideSession, ServerSideSessionInterface

from pymongo import MongoClient, version


class MongoDBSession(ServerSideSession):
    pass


class MongoDBSessionInterface(ServerSideSessionInterface):
    """A Session interface that uses mongodb as session storage. (`pymongo` required)

    :param client: A ``pymongo.MongoClient`` instance.
    :param key_prefix: A prefix that is added to all MongoDB store keys.
    :param use_signer: Whether to sign the session id cookie or not.
    :param permanent: Whether to use permanent session or not.
    :param sid_length: The length of the generated session id in bytes.
    :param serialization_format: The serialization format to use for the session data.
    :param db: The database you want to use.
    :param collection: The collection you want to use.

    .. versionadded:: 0.7
        The `serialization_format` and `app` parameters were added.

    .. versionadded:: 0.6
        The `sid_length` parameter was added.

    .. versionadded:: 0.2
        The `use_signer` parameter was added.
    """

    session_class = MongoDBSession
    ttl = True

    def __init__(
        self,
        client: Optional[MongoClient] = Defaults.SESSION_MONGODB,
        key_prefix: str = Defaults.SESSION_KEY_PREFIX,
        use_signer: bool = Defaults.SESSION_USE_SIGNER,
        permanent: bool = Defaults.SESSION_PERMANENT,
        sid_length: int = Defaults.SESSION_SID_LENGTH,
        serialization_format: str = Defaults.SESSION_SERIALIZATION_FORMAT,
        db: str = Defaults.SESSION_MONGODB_DB,
        collection: str = Defaults.SESSION_MONGODB_COLLECT,
    ):

        if client is None:
            client = MongoClient()

        self.client = client
        self.store = client[db][collection]
        self.use_deprecated_method = int(version.split(".")[0]) < 4

        # Create a TTL index on the expiration time, so that mongo can automatically delete expired sessions
        self.store.create_index("expiration", expireAfterSeconds=0)

        super().__init__(
            None, key_prefix, use_signer, permanent, sid_length, serialization_format
        )

    def _retrieve_session_data(self, store_id: str) -> Optional[dict]:
        # Get the saved session (document) from the database
        document = self.store.find_one({"id": store_id})
        if document:
            serialized_session_data = want_bytes(document["val"])
            return self.serializer.decode(serialized_session_data)
        return None

    def _delete_session(self, store_id: str) -> None:
        if self.use_deprecated_method:
            self.store.remove({"id": store_id})
        else:
            self.store.delete_one({"id": store_id})

    def _upsert_session(
        self, session_lifetime: TimeDelta, session: ServerSideSession, store_id: str
    ) -> None:
        storage_expiration_datetime = datetime.utcnow() + session_lifetime

        # Serialize the session data
        serialized_session_data = self.serializer.encode(session)

        # Update existing or create new session in the database
        if self.use_deprecated_method:
            self.store.update(
                {"id": store_id},
                {
                    "id": store_id,
                    "val": serialized_session_data,
                    "expiration": storage_expiration_datetime,
                },
                True,
            )
        else:
            self.store.update_one(
                {"id": store_id},
                {
                    "$set": {
                        "id": store_id,
                        "val": serialized_session_data,
                        "expiration": storage_expiration_datetime,
                    }
                },
                True,
            )
