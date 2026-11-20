# Upstream JavaScript client canary

Run from the repository root with Node 24, npm and Git. The job needs access to GitHub and the npm registry and permission to bind a loopback port.

```sh
npm ci --prefix packages/typescript
bash tests/upstream-js/run.sh
```

The runner builds the official client from a [pinned upstream commit](https://github.com/a2aproject/a2a-js/commit/5e6f990342d72e4440433782795c066703fc8a85) in a temporary directory using its lockfile. It starts the local TypeScript Lite agent with its own locked SDK. For JSON-RPC and HTTP+JSON it checks the selected binding, discovered endpoint, request-hook order, transmission of the hook-supplied API key, and the response to a real echo call. Each successful binding prints a JSON record. Any failed assertion exits the job with an error.

Use this as a separate weekly compatibility check. Update the SHA deliberately after reviewing changes to the [endpoint API](https://github.com/a2aproject/a2a-js/pull/829) and [client hooks](https://github.com/a2aproject/a2a-js/pull/838).
