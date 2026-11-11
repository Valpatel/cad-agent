**Fixed**
- Full CI provisioning uses the hosted runner's existing Canonical HTTPS mirror fallbacks with bounded transport failover when a mirror stalls; dependency packages, signature verification and required tests remain unchanged (#576).
