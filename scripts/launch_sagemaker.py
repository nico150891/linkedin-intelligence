#!/usr/bin/env python3
"""Launch a SageMaker Processing Job to run the linkedin-intel pipeline with Ollama.

Uploads project code + data to S3, runs the pipeline on a GPU instance,
and downloads results when complete.

Usage:
    # With GDPR export only (profile parsing + GDPR analysis)
    python scripts/launch_sagemaker.py --gdpr-path data/raw/gdpr_export/

    # With GDPR + scraped jobs (full pipeline)
    python scripts/launch_sagemaker.py \\
        --gdpr-path data/raw/gdpr_export/ \\
        --jobs-path data/raw/jobs_scraped/

    # Dry run (show what would happen)
    python scripts/launch_sagemaker.py --gdpr-path data/sample/gdpr/ --dry-run

    # With sample data (quick test)
    python scripts/launch_sagemaker.py --gdpr-path data/sample/gdpr/ \\
        --jobs-path data/sample/
"""

from __future__ import annotations

import argparse
import datetime
import os
import subprocess
import sys
import time
from pathlib import Path

import boto3

# ── Defaults ─────────────────────────────────────────────────────────────────
ACCOUNT = "465983268775"
REGION = "eu-west-1"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/SageMakerExecutionRole-S2SuperRes"
BUCKET = f"sagemaker-{REGION}-{ACCOUNT}"
DLC_ACCOUNT = "763104351884"
IMAGE_TAG = "2.5.1-gpu-py311-cu124-ubuntu22.04-sagemaker"
IMAGE_URI = f"{DLC_ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/pytorch-training:{IMAGE_TAG}"
INSTANCE_TYPE = "ml.g4dn.xlarge"
VOLUME_SIZE_GB = 50
MAX_RUNTIME_SECONDS = 3600  # 1 hour
S3_PREFIX = "linkedin-intelligence"


def _upload_dir(local_path: Path, s3_uri: str) -> None:
    """Upload a local directory to S3 using the AWS CLI (handles large trees fast)."""
    cmd = [
        "aws", "s3", "sync",
        str(local_path), s3_uri,
        "--quiet",
        "--exclude", "__pycache__/*",
        "--exclude", "*.pyc",
        "--exclude", ".venv/*",
        "--exclude", ".git/*",
        "--exclude", ".mypy_cache/*",
        "--exclude", ".ruff_cache/*",
        "--exclude", ".pytest_cache/*",
        "--exclude", "*.egg-info/*",
        "--exclude", "data/raw/*",
        "--exclude", "data/processed/*",
    ]
    subprocess.run(cmd, check=True)


def _download_dir(s3_uri: str, local_path: Path) -> None:
    """Download results from S3."""
    local_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["aws", "s3", "sync", s3_uri, str(local_path), "--quiet"],
        check=True,
    )


def _create_processing_job(
    sagemaker: object,
    job_name: str,
    code_s3: str,
    gdpr_s3: str,
    jobs_s3: str | None,
    output_s3: str,
    model: str,
) -> None:
    """Create the SageMaker Processing Job via boto3."""
    inputs = [
        {
            "InputName": "code",
            "S3Input": {
                "S3Uri": code_s3,
                "LocalPath": "/opt/ml/processing/input/code",
                "S3DataType": "S3Prefix",
                "S3InputMode": "File",
                "S3DataDistributionType": "FullyReplicated",
            },
        },
        {
            "InputName": "gdpr",
            "S3Input": {
                "S3Uri": gdpr_s3,
                "LocalPath": "/opt/ml/processing/input/gdpr",
                "S3DataType": "S3Prefix",
                "S3InputMode": "File",
                "S3DataDistributionType": "FullyReplicated",
            },
        },
    ]

    if jobs_s3:
        inputs.append(
            {
                "InputName": "jobs",
                "S3Input": {
                    "S3Uri": jobs_s3,
                    "LocalPath": "/opt/ml/processing/input/jobs",
                    "S3DataType": "S3Prefix",
                    "S3InputMode": "File",
                    "S3DataDistributionType": "FullyReplicated",
                },
            }
        )

    sagemaker.create_processing_job(  # type: ignore[union-attr]
        ProcessingJobName=job_name,
        ProcessingResources={
            "ClusterConfig": {
                "InstanceCount": 1,
                "InstanceType": INSTANCE_TYPE,
                "VolumeSizeInGB": VOLUME_SIZE_GB,
            }
        },
        AppSpecification={
            "ImageUri": IMAGE_URI,
            "ContainerEntrypoint": [
                "bash",
                "/opt/ml/processing/input/code/scripts/sagemaker_entrypoint.sh",
            ],
            "ContainerArguments": [],
        },
        Environment={
            "OLLAMA_MODEL": model,
        },
        ProcessingInputs=inputs,
        ProcessingOutputConfig={
            "Outputs": [
                {
                    "OutputName": "results",
                    "S3Output": {
                        "S3Uri": output_s3,
                        "LocalPath": "/opt/ml/processing/output",
                        "S3UploadMode": "EndOfJob",
                    },
                }
            ]
        },
        RoleArn=ROLE_ARN,
        StoppingCondition={"MaxRuntimeInSeconds": MAX_RUNTIME_SECONDS},
    )


def _wait_for_job(sagemaker: object, job_name: str) -> str:
    """Poll until the Processing Job completes. Returns final status."""
    print("Waiting for job to complete...")
    start = time.time()

    while True:
        resp = sagemaker.describe_processing_job(ProcessingJobName=job_name)  # type: ignore[union-attr]
        status = resp["ProcessingJobStatus"]
        elapsed = int(time.time() - start)
        mins, secs = divmod(elapsed, 60)

        print(f"  [{mins:02d}:{secs:02d}] Status: {status}", end="\r")

        if status in ("Completed", "Failed", "Stopped"):
            print()
            if status == "Failed":
                reason = resp.get("FailureReason", "unknown")
                print(f"FAILED: {reason}")
            return status

        time.sleep(30)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Launch SageMaker Processing Job for linkedin-intel pipeline"
    )
    parser.add_argument(
        "--gdpr-path",
        type=Path,
        required=True,
        help="Local path to GDPR export directory",
    )
    parser.add_argument(
        "--jobs-path",
        type=Path,
        default=None,
        help="Local path to scraped jobs directory (optional)",
    )
    parser.add_argument(
        "--model",
        default="qwen2.5:7b",
        help="Ollama model to use (default: qwen2.5:7b)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/sagemaker"),
        help="Local directory to download results (default: output/sagemaker)",
    )
    parser.add_argument(
        "--instance-type",
        default=INSTANCE_TYPE,
        help=f"SageMaker instance type (default: {INSTANCE_TYPE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be uploaded and launched, without executing",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Launch the job and exit without waiting for completion",
    )
    args = parser.parse_args()

    # ── Validate inputs ──────────────────────────────────────────────────────
    if not args.gdpr_path.exists():
        print(f"ERROR: GDPR path does not exist: {args.gdpr_path}")
        sys.exit(1)

    if args.jobs_path and not args.jobs_path.exists():
        print(f"ERROR: Jobs path does not exist: {args.jobs_path}")
        sys.exit(1)

    project_root = Path(__file__).resolve().parent.parent
    if not (project_root / "pyproject.toml").exists():
        print(f"ERROR: Cannot find project root at {project_root}")
        sys.exit(1)

    # ── Build S3 paths ───────────────────────────────────────────────────────
    ts = datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%d-%H%M%S")
    job_name = f"linkedin-intel-{ts}"

    code_s3 = f"s3://{BUCKET}/{S3_PREFIX}/code/"
    gdpr_s3 = f"s3://{BUCKET}/{S3_PREFIX}/input/gdpr/"
    jobs_s3 = f"s3://{BUCKET}/{S3_PREFIX}/input/jobs/" if args.jobs_path else None
    output_s3 = f"s3://{BUCKET}/{S3_PREFIX}/output/{job_name}/"

    # ── Dry run ──────────────────────────────────────────────────────────────
    print(f"Job name:      {job_name}")
    print(f"Instance:      {args.instance_type}")
    print(f"Model:         {args.model}")
    print(f"Image:         {IMAGE_URI}")
    print(f"Role:          {ROLE_ARN}")
    print()
    print(f"Upload code:   {project_root} -> {code_s3}")
    print(f"Upload GDPR:   {args.gdpr_path} -> {gdpr_s3}")
    if jobs_s3:
        print(f"Upload jobs:   {args.jobs_path} -> {jobs_s3}")
    print(f"Output:        {output_s3} -> {args.output_dir}")
    print()

    if args.dry_run:
        print("[DRY RUN] Would launch the job above. Exiting.")
        return

    # ── Upload to S3 ─────────────────────────────────────────────────────────
    print("Uploading code...")
    _upload_dir(project_root, code_s3)

    print("Uploading GDPR data...")
    _upload_dir(args.gdpr_path, gdpr_s3)

    if args.jobs_path:
        print("Uploading scraped jobs...")
        _upload_dir(args.jobs_path, jobs_s3)  # type: ignore[arg-type]

    # ── Launch job ───────────────────────────────────────────────────────────
    sagemaker = boto3.client("sagemaker", region_name=REGION)

    print(f"\nLaunching Processing Job: {job_name}")
    _create_processing_job(
        sagemaker,
        job_name=job_name,
        code_s3=code_s3,
        gdpr_s3=gdpr_s3,
        jobs_s3=jobs_s3,
        output_s3=output_s3,
        model=args.model,
    )
    print("Job submitted.")

    console_url = (
        f"https://{REGION}.console.aws.amazon.com/sagemaker/home"
        f"?region={REGION}#/processing-jobs/{job_name}"
    )
    print(f"Console: {console_url}")

    if args.no_wait:
        print("\n--no-wait specified. Check status with:")
        print(f"  aws sagemaker describe-processing-job --processing-job-name {job_name}")
        return

    # ── Wait and download ────────────────────────────────────────────────────
    print()
    status = _wait_for_job(sagemaker, job_name)

    if status == "Completed":
        print(f"\nDownloading results to {args.output_dir}...")
        _download_dir(output_s3, args.output_dir)
        print(f"\nDone! Results in: {args.output_dir}/")
        subprocess.run(["ls", "-lh", str(args.output_dir)])
    else:
        print(f"\nJob ended with status: {status}")
        print("Check logs in CloudWatch:")
        print(f"  /aws/sagemaker/ProcessingJobs/{job_name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
