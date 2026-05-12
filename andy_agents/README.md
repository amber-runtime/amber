# How to use weather_agent.py

**.env file needs these env variables**

```
OPENAI_API_KEY=
DBOS_SYSTEM_DATABASE_URL=
OPENAI_MODEL=gpt-5.4-mini
DBOS_CONDUCTOR_KEY=
```

For `DBOS_SYSTEM_DATABASE_URL` it is a postgresql url.

For `DBOS_CONDUCTOR_KEY` it is the api key you generate on conductor.


## How to run application
```
uv run uvicorn andy_agents.weather_agent:app --reload
```

## To access the swagger.ui for fastapi to test your endpoints

http://127.0.0.1:8000/docs

## Accessing psql database
```
psql [DBOS_SYSTEM_DATABASE_URL]
```

## Queries for dbos

**Selecting 10 workflow status**
```
SELECT workflow_uuid, status, name, created_at, updated_at
FROM dbos.workflow_status
ORDER BY created_at DESC
LIMIT 10;
```

**Showing all the tables in dbos**
```
\dt dbos.*
```
