# Dependency checks

Run these checks with freshly resolved dependencies for the commit under review:

```sh
uvx pip-audit --path packages/python/.venv/lib/python3.12/site-packages
npm audit --prefix packages/typescript
cd packages/java
./gradlew writeInteropClasspath --no-daemon
cd ../..
python3 tests/security/audit_java.py --output /tmp/a2alite-java-audit.json
```

Adjust the Python site-packages path to the interpreter used by the environment.
Install optional dependencies used in the deployment before auditing; an absent
optional provider is outside the scan. The Java check covers the resolved test
runtime, including Javalin and the PostgreSQL driver, and sends only public Maven
coordinates to OSV. A service failure fails the check instead of reporting a clean
scan. Store the report with the release evidence; advisory databases change over time.

Review advisories and upgrade direct dependencies or add a narrowly documented
constraint. Do not use `npm audit fix`. A clean dependency scan does not validate
application authorization, callback policy, recovery correctness or deployment security;
those have separate contract tests.
