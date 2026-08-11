import unittest
from pathlib import Path
from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from scripts.bootstrap_aws import (
    PARAMETER_NAMES,
    github_trust_policy,
    store_secure_parameters,
)


ROOT = Path(__file__).resolve().parent.parent


class ParameterBootstrapTests(unittest.TestCase):
    def test_all_provider_values_are_written_as_secure_strings(self):
        ssm = MagicMock()
        ssm.get_parameter.side_effect = ClientError(
            {"Error": {"Code": "ParameterNotFound", "Message": "missing"}},
            "GetParameter",
        )
        answers = iter(["gateway", "openai", "mem0", "firecrawl"])

        stored = store_secure_parameters(ssm, prompt=lambda _: next(answers))

        self.assertEqual(stored, list(PARAMETER_NAMES))
        self.assertEqual(ssm.put_parameter.call_count, 4)
        for call, name in zip(ssm.put_parameter.call_args_list, PARAMETER_NAMES):
            self.assertEqual(call.kwargs["Name"], name)
            self.assertEqual(call.kwargs["Type"], "SecureString")
            self.assertTrue(call.kwargs["Overwrite"])

    def test_blank_input_keeps_an_existing_parameter_without_reading_it(self):
        ssm = MagicMock()
        ssm.get_parameter.return_value = {"Parameter": {"Name": PARAMETER_NAMES[0]}}

        stored = store_secure_parameters(ssm, names=[PARAMETER_NAMES[0]], prompt=lambda _: "")

        self.assertEqual(stored, [])
        ssm.get_parameter.assert_called_once_with(
            Name=PARAMETER_NAMES[0],
            WithDecryption=False,
        )
        ssm.put_parameter.assert_not_called()

    def test_blank_input_cannot_create_a_missing_required_parameter(self):
        ssm = MagicMock()
        ssm.get_parameter.side_effect = ClientError(
            {"Error": {"Code": "ParameterNotFound", "Message": "missing"}},
            "GetParameter",
        )

        with self.assertRaisesRegex(ValueError, "required"):
            store_secure_parameters(
                ssm,
                names=[PARAMETER_NAMES[0]],
                prompt=lambda _: "",
            )


class GitHubOIDCTests(unittest.TestCase):
    def test_trust_is_restricted_to_super_claude_main(self):
        trust = github_trust_policy("209479275988")
        condition = trust["Statement"][0]["Condition"]

        self.assertEqual(
            condition["StringEquals"]["token.actions.githubusercontent.com:sub"],
            "repo:Cramer-69/Super-Claude:ref:refs/heads/main",
        )
        self.assertEqual(
            condition["StringEquals"]["token.actions.githubusercontent.com:aud"],
            "sts.amazonaws.com",
        )


class DeploymentManifestTests(unittest.TestCase):
    def test_docker_image_uses_cloud_dependencies(self):
        dockerfile = (ROOT / "Dockerfile").read_text()

        self.assertIn("COPY requirements-cloud.txt", dockerfile)
        self.assertIn("pip install --no-cache-dir -r requirements-cloud.txt", dockerfile)
        self.assertNotIn("ffmpeg", dockerfile.lower())

    def test_ecr_workflow_has_actionable_role_preflight(self):
        workflow = (ROOT / ".github/workflows/aws-ecr-build-push.yml").read_text()

        self.assertIn("Preflight AWS role variable", workflow)
        self.assertIn("AWS_ROLE_ARN is missing", workflow)
        self.assertIn("${{ github.sha }}", workflow)
        self.assertIn(":latest", workflow)

    def test_app_runner_manifest_has_cost_and_secret_boundaries(self):
        template = (ROOT / "infra/aws-conductor.yaml").read_text()

        self.assertIn("MaxSize: 1", template)
        self.assertIn("Cpu: 1 vCPU", template)
        self.assertIn("Memory: 2 GB", template)
        self.assertIn('Port: "8080"', template)
        self.assertIn("Path: /health/live", template)
        self.assertIn("RuntimeEnvironmentSecrets:", template)
        for name in ("CONDUCTOR_API_KEY", "OPENAI_API_KEY", "MEM0_API_KEY", "FIRECRAWL_API_KEY"):
            self.assertIn(f"Name: {name}", template)
        self.assertIn("Threshold: 10", template)
        self.assertIn("Threshold: 20", template)
        self.assertIn("Threshold: 25", template)


if __name__ == "__main__":
    unittest.main()
