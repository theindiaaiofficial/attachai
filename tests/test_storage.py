"""Storage pagination, path traversal protection, and collision-free path tests."""

from __future__ import annotations

import unittest

from app.core.exceptions import ProviderError
from app.utils.validators import build_storage_object_path
from tests.conftest import IsolatedOrbitTestEnv


class TestStorage(unittest.TestCase):
    def setUp(self) -> None:
        self.env = IsolatedOrbitTestEnv()

    def tearDown(self) -> None:
        self.env.cleanup()

    def test_collision_free_storage_path_builder(self) -> None:
        _, path1 = build_storage_object_path("tenant-1", "src-aaa", "pricing.pdf")
        _, path2 = build_storage_object_path("tenant-1", "src-bbb", "pricing.pdf")
        self.assertNotEqual(path1, path2)
        self.assertEqual(path1, "tenant-1/src-aaa/pricing.pdf")
        self.assertEqual(path2, "tenant-1/src-bbb/pricing.pdf")

    def test_path_traversal_rejected(self) -> None:
        with self.assertRaises(ProviderError):
            self.env.container.storage_provider.upload("../../etc/passwd", b"bad")

    def test_paginated_listing_and_tenant_deletion_over_multiple_pages(self) -> None:
        tenant_id = "tenant_paginated"
        for i in range(25):
            self.env.container.storage_provider.upload(f"{tenant_id}/src_{i}/doc_{i}.txt", f"content {i}".encode())

        listed = self.env.container.storage_provider.list_objects(tenant_id, page_size=7)
        self.assertEqual(len(listed), 25)

        deleted_count = self.env.container.storage_provider.delete_tenant_objects(tenant_id, page_size=7)
        self.assertEqual(deleted_count, 25)
        self.assertEqual(len(self.env.container.storage_provider.list_objects(tenant_id)), 0)


if __name__ == "__main__":
    unittest.main()
