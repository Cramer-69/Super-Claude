#!/usr/bin/env python3
"""Deploy one immutable ECR image to the bounded App Runner stack."""

import argparse
import subprocess
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from scripts.bootstrap_aws import ECR_REPOSITORY, REGION


ROOT = Path(__file__).resolve().parent.parent
STACK_NAME = "super-claude-conductor"


def _default_image_tag() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _default_budget_email() -> str:
    return subprocess.run(
        ["git", "config", "user.email"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="fabric")
    parser.add_argument("--region", default=REGION)
    parser.add_argument("--image-tag", default=_default_image_tag())
    parser.add_argument("--budget-email", default=_default_budget_email())
    return parser.parse_args()


def deploy_stack(cloudformation, image_identifier: str, budget_email: str) -> str:
    kwargs = {
        "StackName": STACK_NAME,
        "TemplateBody": (ROOT / "infra/aws-conductor.yaml").read_text(),
        "Parameters": [
            {"ParameterKey": "ImageIdentifier", "ParameterValue": image_identifier},
            {"ParameterKey": "BudgetEmail", "ParameterValue": budget_email},
        ],
        "Capabilities": ["CAPABILITY_NAMED_IAM"],
    }
    try:
        cloudformation.describe_stacks(StackName=STACK_NAME)
    except ClientError as error:
        if "does not exist" not in str(error):
            raise
        cloudformation.create_stack(**kwargs)
        cloudformation.get_waiter("stack_create_complete").wait(StackName=STACK_NAME)
    else:
        try:
            cloudformation.update_stack(**kwargs)
        except ClientError as error:
            if "No updates are to be performed" not in str(error):
                raise
        else:
            cloudformation.get_waiter("stack_update_complete").wait(StackName=STACK_NAME)

    stack = cloudformation.describe_stacks(StackName=STACK_NAME)["Stacks"][0]
    outputs = {item["OutputKey"]: item["OutputValue"] for item in stack["Outputs"]}
    return outputs["ServiceUrl"]


def main() -> int:
    args = parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    ecr = session.client("ecr")
    repository = ecr.describe_repositories(
        repositoryNames=[ECR_REPOSITORY]
    )["repositories"][0]
    ecr.describe_images(
        repositoryName=ECR_REPOSITORY,
        imageIds=[{"imageTag": args.image_tag}],
    )
    image_identifier = f"{repository['repositoryUri']}:{args.image_tag}"
    service_url = deploy_stack(
        session.client("cloudformation"),
        image_identifier,
        args.budget_email,
    )
    print(service_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
