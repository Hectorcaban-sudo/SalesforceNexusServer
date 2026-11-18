# Execute a pipeline by API

Version 1.5.0 adds a direct way to run a saved pipeline and get the result back.

## Endpoint

```
POST /api/execute/{project}/pipeline/{pipeline_id}
```

`project` is a project id or a project name. `pipeline_id` is the pipeline id. The pipeline must belong to that project.

Body:

```json
{
  "payload": {
    "User_Message__c": "show me the latest modification for Project 4130650"
  },
  "org_id": "optional"
}
```

The response includes the result, the transaction id, and the node trace. The call is recorded as a transaction.

## Auth

Either a login token or a consumer key and secret.

Login token (operator or higher):

```
Authorization: Bearer <token>
```

Get a token with `POST /api/auth/login`.

Consumer key and secret:

```
X-Consumer-Key: <key>
X-Consumer-Secret: <secret>
```

Create a client under Administration → API clients, or on the Security page, API clients tab. The secret is shown once. A client can be limited to one project. Disable or delete a client to revoke it.

## Swagger

FastAPI serves the OpenAPI spec. No extra setup.

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- Raw spec: `/openapi.json`

## Other execute endpoints

These still take a login token only:

- `POST /api/execute/dss-client`
- `POST /api/execute/langflow`
