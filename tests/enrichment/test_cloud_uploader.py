"""tests/enrichment/test_cloud_uploader.py — Cloud uploader unit tests.

Tests dry-run mode, URL generation, and error handling.
No live S3 calls.
"""
import sys
import os
import tempfile

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from cloud_uploader import S3Uploader


class TestDryRunMode:

    def test_default_is_dry_run(self):
        up = S3Uploader()
        assert up.dry_run is True
        assert up.mode == "dry_run"

    def test_from_env_no_creds_is_dry_run(self):
        """Without env vars, uploader defaults to dry-run."""
        for k in ("S3_ENDPOINT_URL", "S3_BUCKET_NAME", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
            os.environ.pop(k, None)
        up = S3Uploader.from_env()
        assert up.dry_run is True

    def test_force_dry_run_via_env(self):
        os.environ["S3_DRY_RUN"] = "true"
        os.environ["S3_ENDPOINT_URL"] = "https://s3.example.com"
        os.environ["S3_BUCKET_NAME"] = "test-bucket"
        os.environ["S3_ACCESS_KEY"] = "AKID"
        os.environ["S3_SECRET_KEY"] = "SECRET"
        try:
            up = S3Uploader.from_env()
            assert up.dry_run is True
        finally:
            for k in ("S3_DRY_RUN", "S3_ENDPOINT_URL", "S3_BUCKET_NAME",
                       "S3_ACCESS_KEY", "S3_SECRET_KEY"):
                os.environ.pop(k, None)

    def test_dry_run_upload_returns_placeholder_url(self):
        up = S3Uploader(bucket_name="mybucket", dry_run=True)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"\xff\xd8test")
            tmp = f.name
        try:
            result = up.upload_file(tmp, "products/honeywell/test.jpg")
            assert result.upload_mode == "dry_run"
            assert "mybucket" in result.public_url
            assert "products/honeywell/test.jpg" in result.public_url
            assert result.error == ""
        finally:
            os.unlink(tmp)


class TestUrlGeneration:

    def test_public_base_url_override(self):
        up = S3Uploader(public_base_url="https://cdn.biretos.ru", dry_run=True)
        url = up._build_dry_run_url("products/honeywell/123.jpg")
        assert url == "https://cdn.biretos.ru/products/honeywell/123.jpg"

    def test_fallback_url_without_base(self):
        up = S3Uploader(bucket_name="test-bucket", dry_run=True)
        url = up._build_dry_run_url("products/honeywell/123.jpg")
        assert url == "https://test-bucket.example.com/products/honeywell/123.jpg"

    def test_live_url_with_endpoint(self):
        up = S3Uploader(
            endpoint_url="https://storage.yandexcloud.net",
            bucket_name="biretos",
            dry_run=False,
        )
        url = up._build_public_url("products/honeywell/123.jpg")
        assert url == "https://storage.yandexcloud.net/biretos/products/honeywell/123.jpg"

    def test_live_url_with_public_base(self):
        up = S3Uploader(
            endpoint_url="https://storage.yandexcloud.net",
            bucket_name="biretos",
            public_base_url="https://cdn.biretos.ru",
            dry_run=False,
        )
        url = up._build_public_url("products/honeywell/123.jpg")
        assert url == "https://cdn.biretos.ru/products/honeywell/123.jpg"


class TestErrorHandling:

    def test_missing_file_returns_error(self):
        up = S3Uploader(dry_run=True)
        result = up.upload_file("/nonexistent/path.jpg", "x/y.jpg")
        assert result.upload_mode == "error"
        assert "file_not_found" in result.error

    def test_batch_mixed_results(self):
        up = S3Uploader(bucket_name="test", dry_run=True)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"\xff\xd8test")
            tmp = f.name
        try:
            results = up.upload_batch([
                (tmp, "ok.jpg"),
                ("/nonexistent.jpg", "fail.jpg"),
            ])
            assert len(results) == 2
            assert results[0].upload_mode == "dry_run"
            assert results[1].upload_mode == "error"
        finally:
            os.unlink(tmp)
