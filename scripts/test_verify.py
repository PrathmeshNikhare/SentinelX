"""Self-test for the pure helpers in verify.py. Run: python -m unittest scripts.test_verify"""

import unittest

from scripts.verify import compose_variables, env_example_keys, forbidden_tracked_paths, parse_compose_ps


class ComposeVariablesTest(unittest.TestCase):
    def test_finds_plain_and_required_forms_and_skips_escapes(self) -> None:
        text = 'a: ${A}\nb: ${B:?set B}\nc: "$$NOT_A_REF"\nd: $${ALSO_ESCAPED}\ne: ${E:-x}'
        self.assertEqual(compose_variables(text), {"A", "B", "E"})


class EnvExampleKeysTest(unittest.TestCase):
    def test_ignores_comments_and_blank_lines(self) -> None:
        text = "# comment\n\nA=1\n  B = two\n#C=3\nD=\n"
        self.assertEqual(env_example_keys(text), {"A", "B", "D"})


class ForbiddenTrackedPathsTest(unittest.TestCase):
    def test_flags_env_files_and_dependency_dirs_only(self) -> None:
        tracked = [
            ".env.example",
            ".env",
            "apps/web/.env.local",
            "apps/web/node_modules/x/index.js",
            "services/ai/.venv/bin/python",
            "docs/env.md",
            "apps/web/src/environment.ts",
        ]
        self.assertEqual(
            forbidden_tracked_paths(tracked),
            [".env", "apps/web/.env.local", "apps/web/node_modules/x/index.js", "services/ai/.venv/bin/python"],
        )


class ParseComposePsTest(unittest.TestCase):
    def test_json_lines(self) -> None:
        out = '{"Service":"postgres","State":"running","Health":"healthy"}\n{"Service":"kafka-init","State":"exited","Health":""}\n'
        self.assertEqual(parse_compose_ps(out), {"postgres": "healthy", "kafka-init": "exited"})

    def test_json_array_and_empty(self) -> None:
        self.assertEqual(parse_compose_ps('[{"Service":"qdrant","Health":"starting"}]'), {"qdrant": "starting"})
        self.assertEqual(parse_compose_ps(""), {})


if __name__ == "__main__":
    unittest.main()
