from __future__ import annotations

import boto3
from botocore.exceptions import BotoCoreError, ClientError


class StorageError(Exception):
    pass


class MinioStorage:
    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket_name: str,
    ) -> None:
        self.bucket_name = bucket_name
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="us-east-1",
        )

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket_name)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchBucket", "NotFound"}:
                self.client.create_bucket(Bucket=self.bucket_name)
            else:
                raise StorageError("unable to verify bucket") from exc
        except BotoCoreError as exc:
            raise StorageError("unable to verify bucket") from exc

    def object_exists(self, object_key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"404", "NotFound"}:
                return False
            raise StorageError("unable to determine object existence") from exc
        except BotoCoreError as exc:
            raise StorageError("unable to determine object existence") from exc

    def upload_object(
        self,
        object_key: str,
        body: bytes,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        extra_args: dict[str, str] = {}
        if content_type:
            extra_args["ContentType"] = content_type
        if metadata:
            extra_args["Metadata"] = metadata
        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=object_key,
                Body=body,
                **extra_args,
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("object upload failed") from exc

    def get_object(self, object_key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=object_key)
            return response["Body"].read()
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("object retrieval failed") from exc

    def get_object_metadata(self, object_key: str) -> dict[str, str]:
        try:
            response = self.client.head_object(Bucket=self.bucket_name, Key=object_key)
            metadata = response.get("Metadata", {})
            result = {**metadata}
            if response.get("ContentType"):
                result["ContentType"] = response["ContentType"]
            return result
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("object metadata retrieval failed") from exc
