# Security

## Reporting Security Issues

If you discover a potential security issue in this project, we ask that you notify AWS Security via our
[vulnerability reporting page](https://aws.amazon.com/security/vulnerability-reporting/). Please do **not**
create a public GitHub issue.

## Security Considerations

This repository contains sample code for an agent evaluation framework. The code is
provided as-is for educational and evaluation purposes. Before deploying to production:

1. **IAM Permissions**: Review and scope down all IAM policies to follow least-privilege principles.
   The framework uses `bedrock:InvokeModel` and `pricing:GetProducts` — restrict these to specific
   model ARNs and regions. The optional exact token-count / cost feature additionally requires
   `bedrock:CountTokens`.
2. **Encryption**: Enable encryption at rest (SSE-KMS) for any S3 buckets storing evaluation traces
   or results. Enable encryption in transit by enforcing TLS 1.2+ on all endpoints.
3. **Input Validation**: Trace files and configuration (YAML/JSON) are validated against schemas
   before processing. Do not load untrusted trace files without inspection.
4. **Secrets Management**: Use AWS Secrets Manager or SSM Parameter Store for API keys and credentials.
   Never commit secrets to source control. The framework uses the boto3 default credential chain.
5. **LLM Judge Security**: When using external LLM providers via LiteLLM, ensure API keys are stored
   securely and rotated regularly. Review judge prompts to prevent prompt injection from trace content.
6. **Logging and Monitoring**: Enable CloudWatch Logs when running evaluations in AWS environments.
   Evaluation results may contain sensitive trace data — restrict access appropriately.

## Shared Responsibility Model

This sample code operates under the [AWS Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/):

- **AWS is responsible for**: Security of the cloud infrastructure, including Amazon Bedrock service
  availability, model hosting, and underlying compute/storage/networking.
- **You are responsible for**: Security in the cloud, including IAM policies, data encryption,
  network configuration, input validation, output filtering, and compliance with applicable regulations.

## Dependencies

This project uses third-party dependencies listed in `pyproject.toml`. Keep dependencies updated
and monitor for known vulnerabilities using `pip audit` or equivalent tools.
