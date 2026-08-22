#!/usr/bin/env python3
"""Create the AWS security boundary without exposing provider credentials."""

import argparse
import getpass
import json
import shutil
import subprocess
from typing import Callable, Iterable

import boto3
from botocore.exceptions import ClientError


REGION = "us-west-2"
REPOSITORY = "Cramer-69/Super-Claude"
ECR_REPOSITORY = "super-claude"
ROLE_NAME = "gha-super-claude"
OIDC_HOST = "token.actions.githubusercontent.com"
PARAMETER_PREFIX = "/super-claude/prod"
PARAMETER_NAMES = (
    f"{PARAMETER_PREFIX}/CONDUCTOR_API_KEY",
    f"{PARAMETER_PREFIX}/OPENAI_API_KEY",
    f"{PARAMETER_PREFIX}/MEM0_API_KEY",
    f"{PARAMETER_PREFIX}/FIRECRAWL_API_KEY",
)


def _parameter_exists(ssm, name: str) -> bool:
    try:
        ssm.get_parameter(Name=name, WithDecryption=False)
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") == "ParameterNotFound":
            return False
        raise
    return True


def store_secure_parameters(
    ssm,
    names: Iterable[str] = PARAMETER_NAMES,
    prompt: Callable[[str], str] = getpass.getpass,
) -> list[str]:
    """Prompt without echo and put only nonblank values as SecureStrings."""
    stored = []
    for name in names:
        exists = _parameter_exists(ssm, name)
        suffix = " (blank keeps existing)" if exists else ""
        value = prompt(f"{name}{suffix}: ")
        if not value:
            if exists:
                continue
            raise ValueError(f"{name} is required")
        ssm.put_parameter(
            Name=name,
            Value=value,
            Type="SecureString",
            Overwrite=True,
        )
        stored.append(name)
    return stored


def github_trust_policy(account_id: str) -> dict:
    """Trust only GitHub's main branch token for this exact repository."""
    return {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {
                "Federated": (
                    f"arn:aws:iam::{account_id}:oidc-provider/{OIDC_HOST}"
                )
            },
            "Action": "sts:AssumeRoleWithWebIdentity",
            "Condition": {
                "StringEquals": {
                    f"{OIDC_HOST}:aud": "sts.amazonaws.com",
                    f"{OIDC_HOST}:sub": (
                        f"repo:{REPOSITORY}:ref:refs/heads/main"
                    ),
                }
            },
        }],
    }


def ecr_push_policy(account_id: str, region: str) -> dict:
    repository_arn = (
        f"arn:aws:ecr:{region}:{account_id}:repository/{ECR_REPOSITORY}"
    )
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "ecr:GetAuthorizationToken",
                "Resource": "*",
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ecr:CreateRepository",
                    "ecr:DescribeRepositories",
                ],
                "Resource": "*",
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:CompleteLayerUpload",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:InitiateLayerUpload",
                    "ecr:PutImage",
                    "ecr:UploadLayerPart",
                ],
                "Resource": repository_arn,
            },
        ],
    }


def ensure_oidc_provider(iam, account_id: str) -> str:
    arn = f"arn:aws:iam::{account_id}:oidc-provider/{OIDC_HOST}"
    providers = iam.list_open_id_connect_providers()["OpenIDConnectProviderList"]
    existing = {item["Arn"] for item in providers}
    if arn not in existing:
        iam.create_open_id_connect_provider(
            Url=f"https://{OIDC_HOST}",
            ClientIDList=["sts.amazonaws.com"],
            Tags=[{"Key": "Application", "Value": "super-claude"}],
        )
    return arn


def ensure_ecr_repository(ecr) -> str:
    try:
        response = ecr.describe_repositories(repositoryNames=[ECR_REPOSITORY])
        repository = response["repositories"][0]
    except ecr.exceptions.RepositoryNotFoundException:
        repository = ecr.create_repository(
            repositoryName=ECR_REPOSITORY,
            imageScanningConfiguration={"scanOnPush": True},
            imageTagMutability="MUTABLE",
            encryptionConfiguration={"encryptionType": "AES256"},
        )["repository"]
    return repository["repositoryUri"]


def ensure_github_role(iam, account_id: str, region: str) -> str:
    trust = github_trust_policy(account_id)
    ensure_oidc_provider(iam, account_id)
    try:
        role = iam.get_role(RoleName=ROLE_NAME)["Role"]
        iam.update_assume_role_policy(
            RoleName=ROLE_NAME,
            PolicyDocument=json.dumps(trust),
        )
    except iam.exceptions.NoSuchEntityException:
        role = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description="GitHub OIDC push access for Cramer-69/Super-Claude main",
            MaxSessionDuration=3600,
            Tags=[{"Key": "Application", "Value": "super-claude"}],
        )["Role"]
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="super-claude-ecr-push",
        PolicyDocument=json.dumps(ecr_push_policy(account_id, region)),
    )
    return role["Arn"]


def set_github_variable(role_arn: str) -> None:
    if not shutil.which("gh"):
        raise RuntimeError("GitHub CLI is not installed")
    subprocess.run(
        [
            "gh",
            "variable",
            "set",
            "AWS_ROLE_ARN",
            "--repo",
            REPOSITORY,
            "--body",
            role_arn,
        ],
        check=True,
    )


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="fabric")
    parser.add_argument("--region", default=REGION)
    parser.add_argument("--skip-github-variable", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    try:
        identity = session.client("sts").get_caller_identity()
    except Exception as error:
        raise SystemExit(
            f"AWS SSO is not active. Run: aws sso login --profile {args.profile}"
        ) from error

    account_id = identity["Account"]
    stored = store_secure_parameters(session.client("ssm"))
    repository_uri = ensure_ecr_repository(session.client("ecr"))
    role_arn = ensure_github_role(session.client("iam"), account_id, args.region)
    if not args.skip_github_variable:
        try:
            set_github_variable(role_arn)
        except (RuntimeError, subprocess.CalledProcessError) as error:
            raise SystemExit(
                "AWS is ready, but GitHub authorization is missing. Run `gh auth login`, "
                "then rerun this script and press Enter to keep every existing key."
            ) from error

    print(f"Stored or updated {len(stored)} encrypted parameters.")
    print(f"ECR repository: {repository_uri}")
    print(f"GitHub OIDC role: {role_arn}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
