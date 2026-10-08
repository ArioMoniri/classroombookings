"""SmartSched pod CI: polls GitHub, runs the quality gates in Docker on the pod, posts commit statuses,
redeploys the deploy branch, serves /ci/. Stdlib only (+ boto3 from python3-boto3 for SSM/CloudWatch)."""

__version__ = "1.0.0"
