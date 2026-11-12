**Fixed**
- Hosted Ubuntu CI accepts the observed `us-east-2.ec2.archive.ubuntu.com` mirror profile and replaces its priority-one endpoint with the existing registered HTTPS mirror. Strict source/keyring/fallback checks remain in place; successful logs identify the recognized input profile.
