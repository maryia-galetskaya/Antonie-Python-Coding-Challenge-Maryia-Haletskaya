# Antonie Books API

A small FastAPI service for book management and read-only author and publisher reports. It uses MongoDB for persistence and a `src`-layout Python package, with domain, application, infrastructure, and HTTP API layers.

## Requirements

- Python **3.14.8** (the project requires `>=3.14.8,<3.15`); install it from [python.org](https://www.python.org/downloads/) or use uv's managed Python install below.
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Docker Engine with the Docker Compose plugin; see [Docker's installation guide](https://docs.docker.com/engine/install/) (Docker Desktop is available for macOS and Windows).

If you use uv to install and select the required interpreter, run this from the project directory:

```sh
uv python install 3.14.8
uv python pin 3.14.8
```

Install uv using the instructions for your operating system in the linked uv guide. Install Docker Engine and its Compose plugin using the linked Docker guide before running the container commands below.

## Install and run locally

Install the locked dependencies, start MongoDB, then launch the API:

```sh
uv sync --locked
docker compose up -d mongo
uv run uvicorn antonie_books.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

The API runs in the foreground. Keep that terminal open and use another terminal in the project directory for seed commands and HTTP examples. Export any custom settings in that terminal too.

The API is at `http://127.0.0.1:8000`. The Compose MongoDB is published at `127.0.0.1:27017`; the API defaults to `mongodb://127.0.0.1:27017` and database `antonie_books`. The API retries MongoDB startup for up to 30 seconds, with each driver operation bounded to 5 seconds. It prepares required indexes and the book ID counter before serving. Runtime database operations also have a 5-second budget and return the safe `503` response when unavailable.

Settings use the `ANTONIE_BOOKS_` prefix:

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANTONIE_BOOKS_APP_NAME` | `Antonie Books API` | FastAPI application title |
| `ANTONIE_BOOKS_MONGO_URI` | `mongodb://127.0.0.1:27017` | MongoDB connection URI |
| `ANTONIE_BOOKS_MONGO_DATABASE` | `antonie_books` | Database name |

Copy `.env.example` to `.env` to create a local settings file, then export its values into the current shell before starting the API or seed command:

```sh
cp .env.example .env
set -a
. ./.env
set +a
```

The application reads environment variables with the `ANTONIE_BOOKS_` prefix; it does not load `.env` files itself. You can edit `.env` or export an individual variable such as `ANTONIE_BOOKS_MONGO_DATABASE=antonie_sandbox` to override a default. The URI can include credentials and standard MongoDB options. Do not point the e2e cleanup fixture at valuable data: it only accepts database names beginning with `antonie_e2e_` and deletes books and authors in that database.

## Docker startup

Build and start the API and persistent MongoDB together:

```sh
docker compose up --build
```

This command also runs in the foreground; use another terminal for the Docker seed command and HTTP examples.

The API is published at `http://127.0.0.1:8000`; MongoDB is published at `127.0.0.1:27017`. Compose configures the API to use `mongodb://mongo:27017/?retryWrites=false` and database `antonie_books`. MongoDB data is kept in the `mongo_data` named volume. Stop the services with `docker compose down`. To intentionally erase that database, remove the volume as well with `docker compose down -v`.

## Seed data

Demo data is **not** inserted automatically when the API starts. Run the seed command explicitly after MongoDB is available:

```sh
uv run antonie-books-seed
```

In the Docker setup, run it in a one-off API container:

```sh
docker compose run --rm api antonie-books-seed
```

The command reads the same `ANTONIE_BOOKS_MONGO_URI` and `ANTONIE_BOOKS_MONGO_DATABASE` settings as the API. Run the seed command before adding user data. It inserts three authors and two demo books under fixed public IDs 1–3 and 1–2. Existing records with those IDs are preserved, so conflicting user records keep their contents; missing demo records are restored if deleted. Re-seeding therefore restores deleted demo records, while API allocated IDs are never reused. The command reserves book IDs 1–2 by raising the counter to at least 2 without lowering it. On a clean database, the next API-created book receives ID 3. The sample books use `2017-01-12T00:00:00+03:00`, stored and returned normalized to UTC (`2017-01-11T21:00:00Z`).

## HTTP API

Interactive OpenAPI documentation is available at [`/docs`](http://127.0.0.1:8000/docs); the alternative ReDoc UI is at `/redoc`, and the OpenAPI JSON is at `/openapi.json`.

Book objects contain `id`, `title`, `publisher`, `author_ids`, expanded `authors`, `pages`, `tags`, `created_at`, and `updated_at`. Public IDs are positive int64 values. The server assigns book IDs; clients cannot set `id` or timestamps. Dates and timestamps are serialized as ISO 8601 values; timestamps are UTC.

### Endpoints

| Method and path | Result |
| --- | --- |
| `POST /books` | Create a book; returns `201`, the created book, and a `Location: /books/{id}` header. |
| `GET /books` | List books with optional author, title, tag, and page filters; returns a page envelope. |
| `GET /books/{book_id}` | Fetch one book. |
| `PATCH /books/{book_id}` | Update one or more supplied editable fields. |
| `DELETE /books/{book_id}` | Delete a book; returns `204` with no response body. |
| `GET /authors` | List seeded/stored authors with their current `book_count`. |
| `GET /authors/{author_id}/books` | List an author's books with pagination. |
| `GET /publishers/{publisher_name}/average_pages` | Return the exact-name publisher's average page count and book count. |

There is no author create, update, or delete endpoint. Author records are currently provisioned by the seed process or by database administration. There is no health-check endpoint or configured Compose healthcheck at present.

### Create, retrieve, update, and delete a book

The following examples assume the seed data has been loaded (demo author IDs are 1, 2, and 3). The `/books/3` examples apply only to a clean database seeded with IDs 1–2; on a used database, use the `Location` header returned by POST to find the created book's ID.

```sh
curl -i -X POST http://127.0.0.1:8000/books \
  -H 'Content-Type: application/json' \
  -d '{"title":"Domain Modeling Made Functional","publisher":"Pragmatic Bookshelf","author_ids":[1],"pages":288,"tags":["DDD","Python"]}'
curl http://127.0.0.1:8000/books/3
curl -X PATCH http://127.0.0.1:8000/books/3 \
  -H 'Content-Type: application/json' \
  -d '{"pages":300,"tags":["DDD","Python","Design"]}'
curl -i -X DELETE http://127.0.0.1:8000/books/3
```

Creation requires non-empty `title` and `publisher`, at least one existing unique `author_ids` entry, and positive `pages`. `tags` defaults to an empty list. Text fields and tags are trimmed; duplicate tags are removed while retaining their first occurrence. Requests reject unknown fields and strict type mismatches. PATCH accepts any non-empty subset of `title`, `publisher`, `author_ids`, `pages`, and `tags`; omitted fields stay unchanged. Null values, an empty PATCH object, IDs, timestamps, and unknown fields are rejected. `created_at` is retained; `updated_at` is set to the current server UTC time at millisecond precision when later than its current value. Equal timestamps within one millisecond are allowed; the stored value never moves backward, including after a system clock adjustment.

### Lists, filters, and pagination

`GET /books` accepts these query parameters:

| Parameter | Behavior |
| --- | --- |
| `author` | Case-insensitive literal substring match against author names; returns books for matching authors. |
| `title` | Case-insensitive literal substring match against titles. |
| `tags` | Repeat the parameter to request multiple tags; a book must contain **all** requested tags (exact, case-sensitive values). |
| `page` | One-based page number; defaults to `1`, must be at least `1`. |
| `limit` | Page size; defaults to `20`, must be in `1..100`. |

All populated filters combine with AND. Title and author search input is treated literally; regex metacharacters are escaped. Results are ordered by ascending book ID. The response shape is `{"items":[...],"page":1,"limit":20,"total":2}`; `total` counts all records matching the filters, before pagination. A page beyond the last page returns an empty `items` list and the same filtered total. `/authors/{author_id}/books` supports the same `page` and `limit` bounds and response shape.

An explicitly supplied empty `author`, `title`, or `tags` filter is invalid and returns `422`; omit a parameter when it should not constrain the search. Title and author matching uses a case-insensitive substring regex, not tokenized/full-text search. Escaping makes regex punctuation literal, but these unanchored substring queries can scan many documents; the current indexes do not provide full-text search or indexed prefix-search performance.

The count and page contents are separate MongoDB reads, so concurrent writes can make `total` and `items` reflect slightly different moments. Pagination is deterministic by ID, but pages are not a cross-request snapshot while records are changing.

Examples:

```sh
curl 'http://127.0.0.1:8000/books?author=harry&title=python&page=1&limit=10'
curl -G http://127.0.0.1:8000/books --data-urlencode 'tags=Python' --data-urlencode 'tags=Development'
curl 'http://127.0.0.1:8000/authors/2/books?page=1&limit=10'
```

### Author and publisher reports

```sh
curl http://127.0.0.1:8000/authors
curl 'http://127.0.0.1:8000/publishers/O%27Reilly%20Media/average_pages'
```

`GET /authors` returns authors ordered by ascending ID. Each object has `id`, `name`, nullable `birth_date`, and `book_count`. The count is calculated from current book-author links and is zero for an author with no books. `GET /publishers/{publisher_name}/average_pages` uses exact, case-sensitive publisher matching and returns `publisher`, floating-point `average_pages`, and `book_count`.

### Status codes and errors

- `200`: successful GET or PATCH.
- `201`: book created.
- `204`: book deleted.
- `404`: the requested book does not exist, the author resource in `GET /authors/{author_id}/books` does not exist, or the requested publisher has no books. The JSON body is `{"error":{"code":"..._not_found","message":"..."}}`.
- `422`: invalid request parameters/body or domain-level invalid value. This includes unknown author IDs supplied in `POST /books` or `PATCH /books/{book_id}`. Domain errors use `{"error":{"code":"...","message":"..."}}`; FastAPI/Pydantic request validation uses FastAPI's standard `{"detail":[...]}` response.
- `503`: MongoDB is unavailable for a request; returns `{"error":{"code":"database_unavailable","message":"The database is temporarily unavailable."}}` and `Retry-After: 1`.
- `500`: unexpected server error; the client receives a generic `internal_server_error` envelope, while details are logged by the server.

Path IDs must be positive int64 values. Invalid query bounds and malformed or invalid request bodies return `422`.

### Differences from the assignment PDF

The HTTP contract uses `author_ids` for author references and `authors` for expanded author details. Book IDs are generated by the server and are not accepted in create requests. The demo author records have an unknown birth date, represented as JSON `null`, rather than an invented date.

## Architecture and persistence

- `domain`: framework-independent book/author entities and invariants.
- `application`: use cases, filters, results, repository ports, and application errors.
- `infrastructure`: MongoDB repositories, document mappers, startup/index initialization, and explicit seed command.
- `api`: FastAPI routes, request/response schemas, typed dependency wiring, and HTTP error handlers.
- `config.py`: environment-backed settings shared by the API and seed command.

FastAPI handlers pass validated request fields to application services and translate their results into HTTP responses. Services depend on repository interfaces; MongoDB implementations provide persistence. The MongoDB collections are `books`, `authors`, and `counters`. Startup ensures unique indexes for public book and author IDs and indexes book author links, publisher, and tags. MongoDB's built-in `_id` remains the internal document key; public numeric IDs are stored separately as BSON int64.

Book IDs come from a single `counters` document (`{"_id":"books","seq":...}`). Each create atomically increments and returns that document in one MongoDB `find_one_and_update`. IDs are monotonic and are not reused after deletes. A failure after allocation may leave a gap, so IDs are unique sequence values rather than a gap-free count. The single counter document is a write-serialization point and can become a bottleneck under high create traffic; the ID generator is isolated behind an application port so another strategy can be introduced if scale requires it.

The counter is initialized to zero only when both books and authors collections are empty. Startup refuses to reconstruct a missing counter if either collection already contains data, because guessing a safe next value could duplicate IDs. Restore the counter together with a consistent database backup. Back up the database collections as one consistent set, including `counters`; do not repair a lost counter by setting it to `count + 1` or `max + 1` without a verified recovery procedure.

Author CRUD and service/database health checks are possible future additions. They are not part of the current routes or deployment configuration.

## AWS infrastructure with Terraform

The optional `terraform/` configuration describes a small AWS hosting setup for the API:

- An internet-facing Application Load Balancer accepts HTTP traffic on port `80`.
- An ECS Fargate service runs two API tasks by default in private subnets across two Availability Zones. The task security group accepts port `8000` only from the load balancer.
- A single NAT Gateway gives private tasks outbound access to pull container images and connect to MongoDB Atlas. Its Elastic IP is output for Atlas network allow-listing.
- The API logs go to a CloudWatch log group with 30-day retention. ECS reads the MongoDB URI from AWS Secrets Manager and receives the database name as a normal environment variable.

MongoDB itself is not created by this Terraform configuration. It assumes a reachable MongoDB Atlas cluster (or another MongoDB deployment) and a Secrets Manager secret containing the MongoDB URI as its **plain SecretString**, for example `mongodb+srv://...`. Before applying, add the Terraform output `nat_gateway_public_ip` to the database provider's network access allow-list. Configure the database user with only the permissions the application needs. The secret must be in the same AWS region as the ECS service.

If the secret uses a customer-managed KMS key, grant the ECS task execution role `kms:Decrypt` for that key as well; the included policy covers Secrets Manager access for a secret encrypted with the default key.

### Prerequisites

- Terraform `>= 1.6.0` and AWS CLI credentials with permission to create VPC, networking, ALB, ECS, IAM, CloudWatch Logs, and Secrets Manager policy resources.
- A built and pushed API container image in a registry ECS can pull from, such as ECR. The image must listen on port `8000` and include the runtime dependencies. The existing `Dockerfile` satisfies this contract. The Terraform configuration does not create an ECR repository or build/push the image.
- A Secrets Manager secret with the MongoDB URI as its raw secret string. Create it outside Terraform so the credential is not written to Terraform state. Example:

  ```sh
  aws secretsmanager create-secret \
    --name antonie-books/mongo-uri \
    --secret-string 'mongodb+srv://USER:PASSWORD@HOST/antonie_books?retryWrites=true&w=majority' \
    --region eu-west-1
  ```

  Keep the returned ARN; it is supplied as `mongo_uri_secret_arn` below. Do not commit real credentials or a populated `terraform.tfvars` file.

### Plan and apply

Run from the repository root. Replace the image URI and secret ARN with your own values; choose an immutable image tag or digest for repeatable deployments.

```sh
terraform -chdir=terraform init
terraform -chdir=terraform plan \
  -var='container_image=123456789012.dkr.ecr.eu-west-1.amazonaws.com/antonie-books:latest' \
  -var='mongo_uri_secret_arn=arn:aws:secretsmanager:eu-west-1:123456789012:secret:antonie-books/mongo-uri-AbCdEf' \
  -var='desired_count=0' \
  -out=tfplan
terraform -chdir=terraform apply tfplan
terraform -chdir=terraform output -raw api_base_url
terraform -chdir=terraform output -raw nat_gateway_public_ip
```

The initial apply uses `desired_count=0` so the network and NAT Gateway are created without starting tasks before Atlas allows their egress IP. Add `nat_gateway_public_ip` to the MongoDB network allow-list, then apply again with the same image and secret variables and `-var='desired_count=2'` (or omit it to use the default). The service's deployment circuit breaker rolls back a failed task deployment. The ALB checks `/openapi.json`, which the current FastAPI app serves without database access; this checks that the process responds, not that MongoDB is healthy.

To tear down the resources, run `terraform -chdir=terraform destroy` with the same variable values. This does not delete the separately managed MongoDB cluster or Secrets Manager secret.

### Scope and limitations

- This is an infrastructure design for the assignment, not a fully production-hardened deployment. It serves **plain HTTP** on port `80`; there is no TLS certificate, HTTPS listener, custom domain, or redirect. Add ACM, DNS, and an HTTPS listener before exposing real user traffic.
- One NAT Gateway is shared by both private subnets to keep the example small. It is a single point of failure and incurs hourly and data processing charges. Production across two Availability Zones would generally use one NAT Gateway per AZ, or VPC endpoints where suitable, with the corresponding higher cost or networking complexity.
- There is no autoscaling policy, WAF, CDN, deployment pipeline, alarms, dashboard, backup policy, or application-level readiness/health endpoint. The task count is fixed by `desired_count` (default `2`).
- The task has broad outbound access so it can reach public registries and MongoDB Atlas. Its inbound access is restricted to the ALB. The Atlas allow-list restricts database ingress to the NAT Gateway's static egress IP; that is network filtering, not private connectivity. Use Atlas PrivateLink/VPC peering where stronger isolation is required.
- The Terraform configuration does not provision MongoDB, ECR, the image, the secret, DNS, or TLS. Image deployment and database setup are separate prerequisites.
- Terraform state contains infrastructure metadata and secret ARNs, though the MongoDB secret value is fetched by ECS at task startup and is not declared as a Terraform secret value. Store remote state in an encrypted, access-controlled backend with locking for team use; the example leaves backend selection to the operator. Protect local state and plan files and never commit them.
- Fargate task defaults are intentionally small (`256` CPU units and `512` MiB). Adjust `task_cpu`, `task_memory`, and `desired_count` after measuring the real workload. No cost estimate is included; AWS charges for the ALB, NAT Gateway, public IPv4/EIP, Fargate, and log ingestion/storage.

Inputs and outputs are documented in `terraform/variables.tf` and `terraform/outputs.tf`. Terraform state is not included in the repository.

## Development checks

```sh
uv run ruff check .
uv run ruff format --check .
uv build
uv run pytest -m unit
```

To apply Ruff formatting, use `uv run ruff format .`. To run the complete test suite, start the e2e Compose services and use the environment assignments below, replacing `uv run pytest -m e2e` with `uv run pytest`.

### End-to-end tests

The e2e stack is separate from the development stack. It uses API port `8001`, MongoDB port `27018`, database `antonie_e2e_books`, and temporary MongoDB storage. Start it, run HTTP tests, then remove its containers:

```sh
docker compose -f compose.e2e.yaml up --build -d
ANTONIE_BOOKS_E2E_URL=http://127.0.0.1:8001 \
ANTONIE_BOOKS_MONGO_URI='mongodb://127.0.0.1:27018/?retryWrites=false' \
ANTONIE_BOOKS_MONGO_DATABASE=antonie_e2e_books \
uv run pytest -m e2e
docker compose -f compose.e2e.yaml down
```

These assignments apply only to the test command and select the isolated stack even if development settings were previously exported from `.env`.

CI runs Ruff lint and format checks, builds the Python distributions and Docker image, then runs unit and end-to-end jobs in parallel against those build artifacts. It stores Python distributions, the e2e image, and test reports as workflow artifacts. The local e2e stack publishes API and MongoDB ports only on `127.0.0.1`. Its fixtures use the configured Mongo URI, wait within bounded budgets for both services, and clean books and authors before and after each test while preserving the allocation counter. The fixture only accepts database names with the `antonie_e2e_` prefix. Tests share a disposable database and run sequentially. E2e MongoDB data disappears when its containers are removed.
