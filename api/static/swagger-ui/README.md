# Local API documentation assets

Swagger UI distribution 5.35.0, from https://www.npmjs.com/package/swagger-ui-dist/v/5.35.0 (upstream: https://github.com/swagger-api/swagger-ui).

These unchanged upstream assets let `/docs` work without loading scripts, CSS or the favicon from a third-party CDN. Apache-2.0 LICENSE, NOTICE and bundled third-party license notices are retained. `manifest.json` records SHA-256 hashes.

To reproduce: install `swagger-ui-dist@5.35.0` with npm into a temporary directory, then copy the six files listed in the manifest from that package. No npm install is required at backend startup.

The hosting setup follows https://fastapi.tiangolo.com/how-to/custom-docs-ui-assets/ . Online schema validation is disabled; the local OpenAPI schema is used.
