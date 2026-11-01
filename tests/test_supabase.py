"""Supabase SQL migration contract, vector dimension validation, and optional provider configuration tests."""

from __future__ import annotations

import os
import unittest

from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.providers.vector import SupabaseVectorProvider
from app.repositories.supabase import SupabaseRepository


class TestSupabaseAndMigrations(unittest.TestCase):
    def setUp(self) -> None:
        self.root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    def test_initial_sql_migration_defines_set_updated_at_before_triggers_and_128_dim_vector(self) -> None:
        sql_path = os.path.join(self.root_dir, "supabase", "migrations", "0001_initial.sql")
        with open(sql_path, "r", encoding="utf-8") as f:
            sql = f.read()

        fn_pos = sql.find("CREATE OR REPLACE FUNCTION public.set_updated_at()")
        trig_pos = sql.find("EXECUTE FUNCTION public.set_updated_at()")
        self.assertGreaterEqual(fn_pos, 0)
        self.assertGreater(trig_pos, fn_pos, "public.set_updated_at() must be defined BEFORE any trigger uses it")

        self.assertIn("vector(128)", sql)
        self.assertIn("match_knowledge_vectors", sql)
        self.assertIn("INSERT INTO storage.buckets (id, name, public)", sql)
        self.assertIn("VALUES ('knowledge', 'knowledge', FALSE)", sql)

        for required_table in SupabaseRepository.REQUIRED_TABLES:
            self.assertIn(f"CREATE TABLE IF NOT EXISTS public.{required_table}", sql)

    def test_additive_feedback_migration_0002_is_idempotent_and_self_contained(self) -> None:
        sql_path = os.path.join(self.root_dir, "supabase", "migrations", "0002_message_feedback.sql")
        with open(sql_path, "r", encoding="utf-8") as f:
            sql = f.read()

        self.assertIn("CREATE OR REPLACE FUNCTION public.set_updated_at()", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS public.message_feedback", sql)

    def test_vector_dimension_mismatch_fails_startup_validation(self) -> None:
        with self.assertRaises(ConfigurationError):
            Settings(embedding_dimensions=128, supabase_vector_dimensions=1536).validate()

        with self.assertRaises(ConfigurationError):
            Settings(embedding_provider="local", embedding_dimensions=256, supabase_vector_dimensions=256).validate()

    def test_optional_integrations_do_not_block_startup_when_disabled(self) -> None:
        # No Qdrant, SMTP, external embeddings, or TTS credentials supplied -> must validate cleanly
        s = Settings.from_env(
            {
                "APP_ENV": "development",
                "DATABASE_PROVIDER": "sqlite",
                "STORAGE_PROVIDER": "local",
                "VECTOR_PROVIDER": "local",
                "LLM_PROVIDER_TYPE": "local",
                "NOTIFICATION_PROVIDER": "outbox",
                "TTS_API_KEY": "some_unused_tts_key_without_provider",
            }
        )
        self.assertFalse(s.tts_enabled)

    def test_only_allowed_origins_and_cors_origins_configured_works_in_production_without_optional_keys(self) -> None:
        # User provides ONLY ALLOWED_ORIGINS and CORS_ORIGINS in production (and even if provider names
        # like supabase / openai-compatible / qdrant / smtp are set without credentials, they fall back safely)
        s = Settings.from_env(
            {
                "APP_ENV": "production",
                "ALLOWED_ORIGINS": "https://app.example.com",
                "CORS_ORIGINS": "https://widget.example.com",
                "DATABASE_PROVIDER": "supabase",
                "STORAGE_PROVIDER": "supabase",
                "VECTOR_PROVIDER": "qdrant",
                "EMBEDDING_PROVIDER": "openai-compatible",
                "LLM_PROVIDER_TYPE": "openai-compatible",
                "NOTIFICATION_PROVIDER": "smtp",
            }
        )
        self.assertEqual(s.allowed_origins, ["https://app.example.com"])
        self.assertEqual(s.cors_origins, ["https://widget.example.com"])
        self.assertIn("https://app.example.com", s.effective_cors_origins)
        self.assertIn("https://widget.example.com", s.effective_cors_origins)
        self.assertEqual(s.database_provider, "sqlite")
        self.assertEqual(s.storage_provider, "local")
        self.assertEqual(s.vector_provider, "local")
        self.assertEqual(s.embedding_provider, "local")
        self.assertEqual(s.llm_provider_type, "local")
        self.assertEqual(s.notification_provider, "outbox")
        self.assertFalse(s.tts_enabled)

    def test_supabase_vector_rpc_passes_explicit_tenant_filter(self) -> None:
        captured: dict = {}

        def fake_rpc(fn_name: str, payload: dict) -> list[dict]:
            captured["fn"] = fn_name
            captured["payload"] = payload
            return [
                {
                    "id": "v1",
                    "source_id": "s1",
                    "source_filename": "doc.txt",
                    "chunk_index": 0,
                    "content": "Verified chunk",
                    "version": 1,
                    "similarity": 0.88,
                }
            ]

        vec = SupabaseVectorProvider(
            supabase_url="https://example.supabase.co",
            service_role_key="service_secret_key",
            dimensions=128,
            rpc_transport=fake_rpc,
        )
        hits = vec.search("tenant-uuid-123", [0.1] * 128, top_k=3, min_similarity=0.25)
        self.assertEqual(captured["fn"], "match_knowledge_vectors")
        self.assertEqual(captured["payload"]["match_client_id"], "tenant-uuid-123")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].client_id, "tenant-uuid-123")


if __name__ == "__main__":
    unittest.main()

