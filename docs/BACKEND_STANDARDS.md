# Backend Engineering Standards

## Table of Contents

1. [Router Responses (FastAPI)](#1-router-responses-fastapi)
2. [Method Inputs & Outputs (Type Safety)](#2-method-inputs--outputs-type-safety)
3. [Database IDs & Document Control](#3-database-ids--document-control)
4. [Keyword-Only Method Signatures](#4-keyword-only-method-signatures)
5. [Error Handling Pattern](#5-error-handling-pattern)
6. [Units in Attribute Names](#6-units-in-attribute-names)
7. [Nullability Has Meaning](#7-nullability-has-meaning)
8. [Database Collection Method Naming & ID Generation](#8-database-collection-method-naming--id-generation)
9. [Database Access Patterns & Ownership](#9-database-access-patterns--ownership)
10. [Enums for Status & State Machines](#10-enums-for-status--state-machines)
11. [Try/Catch is Not Logic](#11-trycatch-is-not-logic)
12. [Clean Code Doesn't Need Comments](#12-clean-code-doesnt-need-comments)
13. [No Dynamic Attribute Access](#13-no-dynamic-attribute-access)
14. [Imports at Top of File](#14-imports-at-top-of-file)
15. [Logging Standards](#15-logging-standards)
16. [Type Safety for Document Models](#16-type-safety-for-document-models)

---

## 1. Router Responses (FastAPI)

**Rule:**
All router endpoints MUST:
- Be `async def` (no sync endpoints)
- Return an explicit response (never return implicitly)

**Decision Tree:**

1. **Simple success (no data to return):**
   - Use `Response(status_code=200)` (or other appropriate status)

2. **Structured data (any fields to return):**
   - Define and return a Pydantic response model
   - Use `response_model=` in decorator

3. **Error cases:**
   - Raise `HTTPException` (never return error dicts)

**Examples:**

```python
# Simple success
from fastapi import Response

@router.post("/trigger")
async def trigger_job() -> Response:
    await run_job()
    return Response(status_code=200)
```

```python
# Structured response
class JobResponse(BaseModel):
    job_id: str
    status: str

@router.post("/job", response_model=JobResponse)
async def create_job() -> JobResponse:
    job = await queue_job()
    return JobResponse(job_id=job.id, status="queued")
```

**Incorrect:**
```python
# Not async
@router.post("/trigger")
def trigger_job() -> Response:  # MUST BE async def
    ...

# Implicit None
@router.post("/trigger")
async def trigger_job():
    await run_job()  # NO RETURN

# Raw dict return
@router.post("/job")
async def create_job() -> dict:
    return {"job_id": "123", "status": "queued"}  # NO RAW DICTS
```

---

## 2. Method Inputs & Outputs (Type Safety)

### Core Principle

Use Pydantic objects to represent **logical concepts** and **communication contracts**, not as a blanket wrapper for all parameters.

### When to Use Pydantic Request Objects

**Use Pydantic for parameters when:**

1. **Cross-context communication** (boundaries where contracts matter):
   - Backend ↔ Frontend (API endpoints)
   - Service ↔ Independent microservice
   - Service ↔ 3rd party API

2. **Multi-method flow** (in-memory vessel passing through 3+ methods):
   - Same object passed through multiple methods
   - Represents a coupled business concept

```python
# API boundary (required)
class CreateUserRequest(BaseModel):
    email: str
    name: str
    password: str

@router.post("/users")
async def create_user(request: CreateUserRequest) -> UserResponse:
    ...

# Multi-method flow (3+ methods)
class PaymentContext(BaseModel):
    user_id: str
    amount_usd_cents: int
    revenuecat_customer_id: str

async def process_payment(*, context: PaymentContext) -> PaymentResult:
    await validate_payment(context=context)
    await charge_revenuecat(context=context)
    await update_subscription(context=context)
    return PaymentResult(...)
```

### When to Use Explicit Parameters (NOT Pydantic)

**Use explicit parameters for internal methods:**
```python
async def create_user(
    *,
    user_id: str,
    email: str,
    name: str,
    created_at_utc: datetime
) -> User:
    ...
```

**Why explicit parameters internally:**
- Developer sees exactly what's needed at call site
- Prevents scope creep (can't add unrelated fields to parameter object)
- Clear dependencies

### Return Types

**Use Pydantic for returns when:**
- Complex/structured data (multiple fields)
- Cross-context responses (API responses, external services)

**Use primitives when:**
- Single value (`bool`, `int`, `str`)

**Never use:**
- Raw `dict` or `list` for structured data

### Summary Decision Tree

**For parameters:**
- API boundary? → Pydantic
- Passed through 3+ methods? → Pydantic
- Internal method (1-2 uses)? → Explicit parameters

**For returns:**
- Structured data? → Pydantic
- API response? → Pydantic
- Single primitive? → Primitive
- Never → Raw dict/list

---

## 3. Database IDs & Document Control

**Rule:**
Never write application logic around MongoDB's `_id` field (or its `id` alias).

Always use explicit, application-defined ID fields:
- `user_id`
- `video_id`
- `product_id`

**Why:**
- `_id` is a MongoDB implementation detail
- Preserves flexibility for migrations, cross-database portability
- Cleaner external integrations (RevenueCat, APIs, logs)

### Primary Key ID Fields

**Rules for primary key IDs:**
1. **Must auto-generate** using UUIDv7 via `new_id()` from `app.common.utils.ids`
2. **Must be unique** (add unique IndexModel)
3. **Must be indexed** (add to `Settings.indexes`)

**Why UUIDv7?** UUIDv7 embeds a millisecond timestamp prefix, so IDs sort
lexicographically by creation time. This gives B-tree index locality on Mongo
inserts and makes IDs naturally orderable without a separate timestamp.
**Never use `uuid4`** for new domain IDs — always go through `new_id()`.

```python
from pydantic import Field
from pymongo import IndexModel, ASCENDING
from app.common.models.base import BaseDocument, register_document
from app.common.utils.ids import new_id

@register_document
class Video(BaseDocument):
    video_id: str = Field(
        default_factory=new_id,
        description="Unique video identifier (UUIDv7)"
    )
    platform: str
    platform_video_id: str

    class Settings:
        name = "videos"
        indexes = [
            IndexModel([("video_id", ASCENDING)], unique=True),
            IndexModel([("platform", ASCENDING), ("platform_video_id", ASCENDING)], unique=True),
        ]
```

### Non-Primary Key ID Fields

Foreign keys or reference IDs to other collections/systems:
- Auto-generation **depends on business logic**
- Indexing **depends on query patterns**
- `unique=False` unless business logic requires uniqueness

```python
@register_document
class UserProduct(BaseDocument):
    user_product_id: str = Field(
        default_factory=new_id,
        description="Primary key (UUIDv7)"
    )  # Primary key - auto-generated

    user_id: str  # Foreign key - NOT auto-generated
    product_id: str  # Foreign key - NOT auto-generated
    revenuecat_purchase_id: str | None = None  # External ID - NOT auto-generated

    class Settings:
        name = "user_products"
        indexes = [
            IndexModel([("user_product_id", ASCENDING)], unique=True),
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("product_id", ASCENDING)]),
        ]
```

### Querying

Always query using application-defined ID fields, never `_id`:

```python
# Correct
user = await User.objects().filter(user_id=user_id).first()

# Incorrect
user = await User.objects().filter(id=user_id).first()
```

---

## 4. Keyword-Only Method Signatures

**Rule:**
All method parameters (except `self` and `cls`) MUST be keyword-only using the `*` syntax.

**Why:**
- Forces explicitness at call sites
- Prevents argument-order bugs
- Improves readability and refactorability

### Standard Pattern

```python
# Instance methods
async def create_user(self, *, user_id: str, email: str, name: str) -> User:
    ...

# Class methods
@classmethod
async def get_user_by_user_id(cls, *, user_id: str) -> Optional["User"]:
    ...

# Static methods
@staticmethod
def validate_email(*, email: str) -> bool:
    ...

# Async methods
async def update_user(self, *, user_id: str, email: str) -> None:
    ...
```

### Call Site Comparison

```python
# Without keyword-only (bad)
create_user(user_id, email, name, created_at)  # What order? Unclear!

# With keyword-only (good)
create_user(
    user_id=user_id,
    email=email,
    name=name,
    created_at_utc=created_at
)  # Crystal clear!
```

### What Goes Before the `*`

Only `self` (instance methods) or `cls` (class methods) can appear before the `*`.

### Exception: Dunder Methods

Standard Python dunder methods can use positional arguments:
```python
def __init__(self, user_id: str, email: str):
    ...
```

### Exception: API Endpoint Methods

FastAPI router endpoint functions are exempt from the keyword-only requirement. FastAPI handles parameter binding automatically via dependency injection, path parameters, query parameters, and request bodies:
```python
@router.post("/users")
async def create_user(request: CreateUserRequest) -> UserResponse:
    # No `*` needed - FastAPI handles parameter binding
    ...

@router.get("/users/{user_id}")
async def get_user(user_id: str, include_details: bool = False) -> UserResponse:
    # Path and query params bound by FastAPI
    ...
```

**Note:** Internal methods called BY endpoints still require keyword-only arguments.

---

## 5. Error Handling Pattern

**Rule:**
Use the `Result[T]` pattern for expected errors. Let unexpected exceptions bubble to top-level handlers.

### Result Class

**Location:** `app/common/utils/result.py`

```python
from typing import Generic, TypeVar, Any
from pydantic import BaseModel, Field
import logging

T = TypeVar('T')
logger = logging.getLogger(__name__)

class Result(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error_message: str | None = None
    error_context: dict[str, Any] = Field(default_factory=dict)
    error_code: Any | None = None
    error_grouping_prefix: str | None = None

    def add_context(self, **kwargs) -> "Result[T]":
        """Add context, warns on duplicates"""
        for key, value in kwargs.items():
            if key in self.error_context:
                logger.warning(f"Context key '{key}' already exists...")
            else:
                self.error_context[key] = value
        return self

    def set_error_grouping_prefix(self, *, prefix: str) -> "Result[T]":
        """Set grouping prefix, keeps first (lowest-level)"""
        if self.error_grouping_prefix:
            logger.warning(f"Prefix already set to '{self.error_grouping_prefix}'...")
        else:
            self.error_grouping_prefix = prefix
        return self

    def get_error_message(self, *, logger_instance: logging.Logger | None = None) -> str:
        """Format: [prefix] message (ids)"""
        if not self.error_message:
            return ""

        log = logger_instance or logger
        if self.error_context:
            log.info(f"Error context: {self.error_context}")

        parts = []
        if self.error_grouping_prefix:
            parts.append(f"[{self.error_grouping_prefix}]")
        parts.append(self.error_message)

        id_fields = {k: v for k, v in self.error_context.items() if k.endswith('_id')}
        if id_fields:
            ids_str = ", ".join(f"{k}={v}" for k, v in id_fields.items())
            return f"{' '.join(parts)} ({ids_str})"

        return ' '.join(parts)
```

### Internal Methods (Expected Errors)

**Pattern:**
- Return `Result[T]` for expected business/integration errors
- Include specific error message at the level where error occurs
- Add all relevant context available at that level
- Set error_code for differentiation at top level

```python
async def extract_products_from_video(
    *,
    video_id: str,
    video_url: str
) -> Result[list[ExtractedProduct]]:
    try:
        # Call LLM for extraction
        products = await llm_extract_products(video_url=video_url)
        return Result(success=True, data=products)

    except LLMTimeoutError as e:
        return Result(
            success=False,
            error_message="LLM extraction timeout",
            error_context={
                "video_id": video_id,
                "timeout_seconds": e.timeout_seconds,
            },
            error_code="LLM_TIMEOUT"
        ).set_error_grouping_prefix(prefix="Video extraction failed")
```

### Top-Level Handlers (Routers)

```python
@router.post("/ingestion/trigger")
async def trigger_ingestion(*, request: IngestionRequest) -> IngestionResponse:
    try:
        result = await process_video_ingestion(
            video_url=request.video_url,
            user_id=request.user_id
        )

        if not result.success:
            logger.error(result.get_error_message(logger_instance=logger))

            if result.error_code == "VIDEO_NOT_FOUND":
                raise HTTPException(status_code=404, detail="Video not found")
            elif result.error_code == "LLM_TIMEOUT":
                raise HTTPException(status_code=504, detail="Extraction timeout")
            else:
                raise HTTPException(status_code=400, detail=result.error_message)

        return IngestionResponse(video_id=result.data.video_id)

    except HTTPException:
        raise

    except Exception as e:
        logger.info(traceback.format_exc())
        logger.error(f"Unexpected ingestion error: video_url={request.video_url}")
        raise HTTPException(status_code=500, detail="Internal server error")
```

### When to Use Result vs Exceptions

**Use Result[T] for:**
- Expected business errors (user not found, validation failures)
- Expected integration errors (LLM timeout, API rate limit)

**Let exceptions bubble for:**
- Unexpected errors (unhandled edge cases)
- Programming errors (type errors, attribute errors)
- Infrastructure failures (database connection lost)

---

## 6. Units in Attribute Names

**Rule:**
All attributes representing measurements MUST include the unit in the field name.

**Format:** `<attribute_name>_<unit>`

### Datetime Fields (Timezone)

```python
from app.common.models.base import UTCDateTime

# Correct - using the project's UTCDateTime type
created_at_utc: UTCDateTime
modified_at_utc: UTCDateTime
scheduled_for_utc: UTCDateTime

# Incorrect
created_at: datetime      # Timezone ambiguous
timestamp: datetime       # Timezone ambiguous
```

**Standard:** Use UTC for all datetime fields. The project provides a `UTCDateTime` type that automatically ensures timezone awareness.

### Duration Fields

```python
# Correct
video_duration_seconds: int
timeout_ms: int
cache_ttl_seconds: int

# Incorrect
duration: int             # Seconds? Minutes? Hours?
timeout: int              # Ambiguous
```

### Size/Storage Fields

```python
# Correct
file_size_bytes: int
max_upload_size_mb: int
chunk_size_bytes: int

# Incorrect
file_size: int            # Bytes? KB? MB?
size: int                 # Ambiguous
```

### Currency/Money Fields

```python
# Correct
price_usd_cents: int      # Store $10.50 as 1050
amount_usd_cents: int

# Incorrect
price: int                # What currency? Cents or dollars?
amount: float             # Floating-point precision issues
```

### Timezone-Aware Datetime Objects

All datetime objects MUST be timezone-aware:

```python
from datetime import datetime, timezone

# Correct
now = datetime.now(timezone.utc)

# Incorrect
now = datetime.now()  # Naive datetime - no timezone
```

---

## 7. Nullability Has Meaning

**Principle:**
Nullability is a schema decision, not a runtime convenience. Nulls must be explicit, intentional, and type-safe.

### Never Use Sentinel Values for Missing Data

**Forbidden sentinel values:**
- Empty strings (`""`)
- Zero values (`0`, `0.0`)
- Empty lists (`[]`) when the absence of data is the real state
- Magic values (`"N/A"`, `"unknown"`, `"null"`)

**Always use `None` to represent missing, unknown, or not-yet-available data.**

```python
# Bad (sentinel values)
user.phone_number = ""        # Is this "no phone" or "empty input"?
user.age = 0                  # Is this "unknown" or "infant"?

# Good (explicit None)
user.phone_number = None      # Clear: user has no phone number
user.age = None               # Clear: age is unknown
```

### Nullability Must Be Explicit in Schema

**Pydantic Models:**
```python
from pydantic import Field
from app.common.models.base import BaseDocument

@register_document
class Product(BaseDocument):
    product_id: str = Field(
        default_factory=new_id,
        description="Primary key (UUIDv7)"
    )
    name: str  # Required - never None
    description: str | None = None  # Optional
    view_count: int = Field(default=0)  # Required with default

    class Settings:
        name = "products"
        indexes = [
            IndexModel([("product_id", ASCENDING)], unique=True),
        ]
```

### Lists vs Nulls

**`None`** → The data is unknown, unavailable, or not applicable
**`[]`** → The data is known and empty

```python
# Clear semantics
video.extracted_products = None  # Extraction not yet attempted
video.extracted_products = []    # Extraction completed, no products found
```

---

## 8. Database Collection Method Naming & ID Generation

**Rule:**
All database collection methods must be explicit, unambiguous, and self-describing.

### Query Method Naming

**Pattern:** `<action>_<entity>_by_<identifier>`

**Action verbs:**
- `get_` → Retrieve single entity, returns `Optional[T]`
- `find_` → Search for entities, returns `list[T]`
- `list_` → List all entities (with optional filters), returns `list[T]`
- `create_` → Create new entity, returns `T`
- `update_` → Update existing entity, returns `T` or `bool`
- `delete_` → Delete entity, returns `bool`
- `exists_` → Check existence, returns `bool`

```python
# Correct (explicit)
@register_document
class User(BaseDocument):
    user_id: str = Field(default_factory=new_id)
    email: str | None = None
    account_provider_id: str | None = None

    class Settings:
        name = "users"
        indexes = [
            IndexModel([("user_id", ASCENDING)], unique=True),
            IndexModel([("email", ASCENDING)]),
        ]

    @classmethod
    async def get_user_by_user_id(cls, *, user_id: str) -> Optional["User"]:
        """Get a user by their user_id (UUID)."""
        return await cls.objects().filter(user_id=user_id).first()

    @classmethod
    async def get_user_by_account_provider_id(
        cls,
        *,
        account_provider_id: str
    ) -> Optional["User"]:
        """Get an active user by their OAuth provider ID."""
        return await cls.objects().filter(
            account_provider_id=account_provider_id,
            is_active=True
        ).first()

    @classmethod
    async def find_users_by_subscription_status(
        cls,
        *,
        is_active: bool
    ) -> list["User"]:
        """Find users by subscription status."""
        return await cls.objects().filter(
            **{"subscription_details.subscription_is_active": is_active}
        ).to_list()

# Incorrect (ambiguous)
@classmethod
async def get_by_id(cls, *, id: str) -> Optional["User"]:
    # Which ID? user_id? MongoDB _id? Unclear!
    ...
```

### Primary Key ID Generation

When an ID field is the primary key, it must be autogenerated by default:

```python
from pydantic import Field

from app.common.utils.ids import new_id

@register_document
class Video(BaseDocument):
    video_id: str = Field(
        default_factory=new_id,
        description="Unique video identifier (UUIDv7)"
    )

    class Settings:
        name = "videos"
        indexes = [
            IndexModel([("video_id", ASCENDING)], unique=True),
        ]
```

---

## 9. Database Access Patterns & Ownership

**Rule:**
Database access logic must be owned by document/collection classes, not scattered across service layers.

### Ownership

**Document/Collection classes own:**
- Query construction
- Database connections (via `BaseDocument.objects()`)
- Collection access
- Update/delete operations

**Service layer owns:**
- Business logic orchestration
- Calling document methods
- External API integration

### Anti-Pattern: Direct Database Access in Services

```python
# Incorrect (service layer doing DB work)
async def deactivate_old_sessions(*, user_id: str, keep_session_id: str):
    client = await get_mongo_client()  # BAD
    collection = client[get_database_name()]["sessions"]  # BAD
    await collection.update_many(query, {"$set": {"is_active": False}})  # BAD

# Correct (document class owns DB logic)
@register_document
class Session(BaseDocument):
    session_id: str = Field(default_factory=new_id)
    user_id: str

    class Settings:
        name = "sessions"
        indexes = [
            IndexModel([("session_id", ASCENDING)], unique=True),
            IndexModel([("user_id", ASCENDING)]),
        ]

    @classmethod
    async def soft_delete_old_sessions(
        cls,
        *,
        user_id: str,
        keep_session_id: str
    ) -> int:
        """Soft delete all sessions for a user except the specified one."""
        result = await cls.objects().filter(
            user_id=user_id
        ).exclude(
            session_id=keep_session_id
        ).update_async(is_active=False)
        return result

# Service layer just orchestrates
async def deactivate_old_sessions(*, user_id: str, keep_session_id: str):
    count = await Session.soft_delete_old_sessions(
        user_id=user_id,
        keep_session_id=keep_session_id
    )
    logger.info(f"Deactivated {count} old sessions")
```

### Using upsert_one for Atomic Operations

`BaseDocument` provides `upsert_one()` for atomic get-or-create:

```python
# Correct - atomic upsert
user, created = await User.upsert_one(
    filter_query={"account_provider_id": provider_id, "is_active": True},
    set_on_insert={
        "user_id": new_id(),
        "email": email,
        "name": name,
    },
    set_always={
        "last_login": datetime.now(timezone.utc),
    }
)

if created:
    logger.info(f"Created new user: user_id={user.user_id}")
else:
    logger.info(f"Updated existing user: user_id={user.user_id}")
```

### Service Layer Rules

**DO:**
- Call document class methods
- Orchestrate multiple document operations
- Handle external APIs

**DON'T:**
- Instantiate database connections
- Access collections directly
- Construct complex queries inline

---

## 10. Enums for Status & State Machines

**Rule:**
Status and state fields MUST use Enums, not raw strings.

### Define Status as Enum

```python
from enum import Enum
from pydantic import Field
from app.common.models.base import BaseDocument, register_document

class ExtractionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

@register_document
class Video(BaseDocument):
    video_id: str = Field(default_factory=new_id)
    extraction_status: ExtractionStatus = Field(default=ExtractionStatus.PENDING)

    class Settings:
        name = "videos"
        indexes = [
            IndexModel([("video_id", ASCENDING)], unique=True),
            IndexModel([("extraction_status", ASCENDING)]),
        ]
```

### Why Enums Matter

```python
# Bad (raw strings) - easy to make typos
video.extraction_status = "complted"  # Typo - no error!
video.extraction_status = "Complete"  # Wrong case - no error!

# Good (enum) - type-safe
video.extraction_status = ExtractionStatus.COMPLETED
video.extraction_status = ExtractionStatus.COMPLTED  # Attribute error!
```

### Centralized State Transitions

State transitions should be centralized in service methods:

```python
class VideoService:
    @staticmethod
    async def mark_extraction_complete(
        *,
        video_id: str,
        extracted_products: list[ExtractedProduct]
    ) -> Result[Video]:
        video = await Video.objects().filter(video_id=video_id).first()

        if video is None:
            return Result(
                success=False,
                error_message="Video not found",
                error_code="VIDEO_NOT_FOUND"
            ).add_context(video_id=video_id)

        if video.extraction_status != ExtractionStatus.PROCESSING:
            return Result(
                success=False,
                error_message="Can only complete videos in processing state",
                error_code="INVALID_TRANSITION"
            ).add_context(
                video_id=video_id,
                current_status=video.extraction_status.value
            )

        video.extraction_status = ExtractionStatus.COMPLETED
        video.extracted_products = extracted_products
        await video.save()
        return Result(success=True, data=video)
```

### Querying by Status

```python
# Correct: Using Enum values
processing_videos = await Video.objects().filter(
    extraction_status=ExtractionStatus.PROCESSING.value
).to_list()

# Correct: Multiple statuses
pending_or_processing = await Video.objects().filter(
    extraction_status__in=[
        ExtractionStatus.PENDING.value,
        ExtractionStatus.PROCESSING.value
    ]
).to_list()

# Incorrect: Raw strings
processing_videos = await Video.objects().filter(
    extraction_status="processing"
).to_list()
```

---

## 11. Try/Catch is Not Logic

**Rule:**
Do not use try/catch blocks for control flow or expected business logic. Write explicit conditionals instead.

### What is a "True Exception"?

**True exceptions (use try/catch):**
- External API failures (LLM timeout, scraper network error)
- Database connection failures
- File system errors

**Expected business logic (do NOT use try/catch):**
- User not found
- Validation failures
- Empty results

### Anti-Pattern: Try/Catch for Control Flow

```python
# Bad (using exceptions for logic)
async def get_user_email(*, user_id: str) -> str:
    try:
        user = await User.get_user_by_user_id(user_id=user_id)
        return user.email
    except UserNotFoundError:
        return "no-reply@example.com"

# Good (explicit logic)
async def get_user_email(*, user_id: str) -> str:
    user = await User.get_user_by_user_id(user_id=user_id)
    if user is None:
        return "no-reply@example.com"
    return user.email
```

### When Try/Catch is Appropriate

```python
# Good (external API failure - LLM call)
async def extract_products(*, video_url: str) -> Result[list[ExtractedProduct]]:
    try:
        response = await litellm.acompletion(
            model="gpt-4o",
            messages=messages,
            timeout=30
        )
        return Result(success=True, data=parse_products(response))
    except litellm.Timeout as e:
        return Result(
            success=False,
            error_message="LLM extraction timeout",
            error_code="LLM_TIMEOUT"
        )
    except litellm.APIConnectionError as e:
        return Result(
            success=False,
            error_message="LLM API connection error",
            error_code="LLM_CONNECTION_ERROR"
        )
```

### Specific Anti-Patterns

```python
# Bad (checking dict keys with try/catch)
try:
    value = data["key"]
except KeyError:
    value = None

# Good
value = data.get("key")

# Bad (checking list index with try/catch)
try:
    first_item = items[0]
except IndexError:
    first_item = None

# Good
first_item = items[0] if items else None
```

---

## 12. Clean Code Doesn't Need Comments

**Principle:**
Comments are generally useless if the code is good and clear. Instead of commenting, refactor to make the code self-explanatory.

### When Comments Are Harmful

Comments that explain **what** the code does are signs of unclear code.

```python
# Bad (comment explains what)
# Get the user's subscription status
is_pro = user.subscription_details.subscription_is_active

# Good (code is self-explanatory)
def has_pro_access(*, user: User) -> bool:
    if user.subscription_details is None:
        return False
    return user.subscription_details.subscription_is_active
```

### When Comments ARE Appropriate

Comments should explain **why**, not **what**:

```python
# Business context
async def calculate_video_limit(*, user: User) -> int:
    # Free users can save 5 videos, pro users unlimited
    # This limit was set based on storage cost analysis (Q4 2024)
    if user.user_is_pro():
        return float('inf')
    return 5

# TODOs
# TODO(author): Add retry logic for failed LLM extractions
# Issue: https://linear.app/your-org/issue/PROJ-123

# Known issues
# FIXME(author): Race condition when processing duplicate video URLs

# Links to external docs
# TikTok API rate limits:
# https://developers.tiktok.com/doc/rate-limits
```

### Comment Markers

- **TODO:** Future work, enhancements
- **FIXME:** Known bugs that need fixing
- **HACK:** Temporary workarounds
- **NOTE:** Important context

### Refactoring > Comments

Instead of commenting:
1. Extract to well-named functions
2. Use descriptive variable names
3. Replace magic numbers with constants
4. Simplify complex logic

### Dead Code Comments

Never comment out code - delete it instead. Git preserves history.

---

## 13. No Dynamic Attribute Access

**Rule:**
Never use `getattr()`, `hasattr()`, or other dynamic attribute access patterns. All attribute access must be direct and explicit through well-defined methods.

**Why:**
- Type safety: Static analyzers can't verify dynamic access
- Refactoring: Renaming attributes won't catch dynamic references
- Readability: Intent is unclear with dynamic access
- Debugging: Errors surface at runtime instead of development time

### Anti-Pattern: Dynamic Attribute Access

```python
# Bad (getattr)
async def get_user_field(*, user: User, field_name: str) -> Any:
    return getattr(user, field_name, None)

# Bad (hasattr for checking)
async def update_user(*, user: User, data: dict) -> User:
    for key, value in data.items():
        if hasattr(user, key):
            setattr(user, key, value)
    return user

# Bad (dynamic method calls)
async def call_method(*, obj: Any, method_name: str) -> Any:
    method = getattr(obj, method_name)
    return await method()
```

### Correct: Direct Access with Well-Defined Methods

```python
# Good (direct attribute access)
async def get_user_email(*, user: User) -> str | None:
    return user.email

# Good (explicit field handling)
async def update_user_profile(
    *,
    user: User,
    email: str | None = None,
    name: str | None = None,
    bio: str | None = None
) -> User:
    if email is not None:
        user.email = email
    if name is not None:
        user.name = name
    if bio is not None:
        user.bio = bio
    await user.save()
    return user

# Good (explicit method mapping if truly needed)
async def process_video_by_platform(*, video: Video) -> Result[None]:
    if video.platform == "tiktok":
        return await process_tiktok_video(video=video)
    elif video.platform == "instagram":
        return await process_instagram_video(video=video)
    else:
        return Result(
            success=False,
            error_message=f"Unknown platform: {video.platform}",
            error_code="UNKNOWN_PLATFORM"
        )
```

### When You Think You Need Dynamic Access

If you find yourself reaching for `getattr`/`hasattr`, consider:

1. **Use explicit conditionals:**
```python
# Bad
value = getattr(config, env_name, default)

# Good
if env_name == "production":
    value = config.production_value
elif env_name == "staging":
    value = config.staging_value
else:
    value = config.default_value
```

2. **Use a dictionary for truly dynamic data:**
```python
# Bad (dynamic attributes on object)
for field in fields:
    value = getattr(obj, field)

# Good (use a dict for dynamic data)
class Config(BaseModel):
    settings: dict[str, Any]

value = config.settings.get(field_name)
```

3. **Define explicit methods for each operation:**
```python
# Bad
method = getattr(scraper, f"scrape_{platform}")
await method(url)

# Good
class ScraperService:
    async def scrape(self, *, platform: str, url: str) -> Result[VideoData]:
        scrapers = {
            "tiktok": self._scrape_tiktok,
            "instagram": self._scrape_instagram,
        }
        scraper = scrapers.get(platform)
        if scraper is None:
            return Result(success=False, error_code="UNKNOWN_PLATFORM")
        return await scraper(url=url)
```

### Exception: Truly Dynamic External Data

Dynamic access is acceptable ONLY when:
1. The attribute/field name comes from an **external source we do not control** (e.g., webhook payload field names, third-party API response keys)
2. The set of possible values is **genuinely unknown at compile time**

**NOT acceptable excuses:**
- "The framework uses it internally" — frameworks have documented, typed APIs
- "It's easier/shorter" — explicitness > brevity
- "We might add more fields later" — add them explicitly when needed

```python
# NOT acceptable (we control these fields)
for field in ["email", "name", "bio"]:
    setattr(user, field, data.get(field))

# Acceptable ONLY if field_name comes from external webhook we don't control
# AND we've validated it against an allowlist
ALLOWED_WEBHOOK_FIELDS = {"status", "event_type", "timestamp"}
if field_name in ALLOWED_WEBHOOK_FIELDS:
    value = webhook_data.get(field_name)
```

Even in these rare cases, prefer parsing into a typed Pydantic model first.

### Benefits of Direct Access

- **IDE support:** Autocomplete, go-to-definition, find references
- **Type checking:** mypy/pyright catch errors at development time
- **Refactoring:** Rename symbol updates all references
- **Searchability:** grep/find works reliably
- **Documentation:** Code is self-documenting

---

## 14. Imports at Top of File

**Rule:**
All imports MUST be at the top of the file, following PEP 8 conventions.

**Import Order (PEP 8):**
1. Standard library imports
2. Third-party imports
3. Local application imports

Separate each group with a blank line.

```python
# Standard library
import logging
from datetime import datetime, timezone

# Third-party
from pydantic import BaseModel, Field
from pymongo import IndexModel, ASCENDING

# Local
from app.common.models.base import BaseDocument, register_document
from app.common.utils.ids import new_id
from app.common.utils.result import Result
```

### Exception: Modal Functions

**Modal files are the ONLY exception.** Modal runs functions in a containerized environment where import time directly affects cold start latency. In Modal files, imports can be placed inside function bodies to defer loading until the function is invoked.

```python
# modal_tasks.py - Modal exception allowed

import modal

app = modal.App("my-project-tasks")

@app.function(image=modal.Image.debian_slim().pip_install("opencv-python"))
async def process_video(*, video_url: str) -> dict:
    # Imports inside function - acceptable ONLY in Modal
    import cv2
    from app.services.video_processor import extract_frames

    # ... function body
```

**Why Modal is different:**
- Modal cold starts load the entire module before running
- Heavy imports (cv2, torch, etc.) can add seconds to cold start
- Function-level imports defer cost until that specific function runs

### Anti-Pattern: Lazy Imports Elsewhere

```python
# Bad (lazy import in non-Modal code)
def process_image(*, image_path: str) -> Image:
    from PIL import Image  # NO - import at top of file
    return Image.open(image_path)

# Good
from PIL import Image

def process_image(*, image_path: str) -> Image:
    return Image.open(image_path)
```

### Circular Import Resolution

If you encounter circular imports, the solution is to refactor, not to use lazy imports:

1. **Extract shared types** to a separate module
2. **Use TYPE_CHECKING** for type-only imports
3. **Restructure dependencies** to break the cycle

```python
# Type-only import (acceptable for circular type references)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User

async def get_user_videos(*, user: "User") -> list[Video]:
    ...
```

---

## 15. Logging Standards

**Rule:**
Use appropriate log levels and always include structured context for debuggability.

### Log Level Selection

| Level | When to Use |
|-------|-------------|
| `error` | Any failure that needs investigation/tracking: exceptions caught, validation failures that indicate bugs, unexpected states |
| `warning` | Degraded behavior that self-recovered, deprecated usage, non-critical issues |
| `info` | Normal operations worth noting: user actions, state transitions, successful completions |
| `debug` | Verbose details for local development only |

**Key rule:** If you're catching an exception and it indicates something went wrong (even if handled), use `logger.error()`, not `debug` or `warning`.

### Required Context in Error Logs

Error logs MUST include:
1. **Relevant IDs** (user_id, video_id, etc.)
2. **The error itself** (use `error=` prefix)
3. **Traceback** (log `traceback.format_exc()` before the error message)

```python
import traceback

# Correct
except ValueError as e:
    logger.info(traceback.format_exc())
    logger.error(
        f"Invalid skin type from onboarding: "
        f"skin_type={session.facial_skin_type}, "
        f"user_id={session.user_id}, error={e}"
    )

# Incorrect
except ValueError as e:
    logger.warning(f"Invalid skin type: {session.facial_skin_type}")  # Missing IDs, wrong level, no traceback
```

### Anti-Patterns

```python
# Bad: debug for production errors
logger.debug(f"Token validation failed: {e}")

# Bad: warning for errors needing tracking
logger.warning(f"Failed to reload session: {error}")

# Bad: missing context
logger.error(f"Invalid value: {value}")  # Which user? Which record?
```

---

## 16. Type Safety for Document Models

**Rule:**
All decorators, query builders, and factory patterns that return or wrap document classes MUST preserve the concrete type for static analysis (Pylance/pyright). If IntelliSense can't resolve `.delete()`, `.update()`, or a class method on a model, the types are wrong.

### Decorators Must Be Generic

Class decorators that register or wrap document models must use a generic TypeVar so the concrete type passes through:

```python
# Bad — erases User to BaseDocument
def register_document(cls: Type[BaseDocument]) -> Type[BaseDocument]:
    _document_registry.append(cls)
    return cls

# After decoration, Pylance sees User as Type[BaseDocument]:
#   User.get_by_user_id(...)  → not found (defined on User, not BaseDocument)
#   user.user_id              → not found
```

```python
# Good — preserves the concrete type
_D = TypeVar("_D", bound="BaseDocument")

def register_document(cls: Type[_D]) -> Type[_D]:
    _document_registry.append(cls)
    return cls

# After decoration, Pylance sees User as Type[User]:
#   User.get_by_user_id(...)  → Optional[User] ✓
#   user.user_id              → str ✓
#   user.delete()             → BaseDocument ✓
```

### Query Builders Must Be Generic

Chainable query builders (like `QuerySet`) must carry the document type through the chain using `Generic[T]`:

```python
# Bad — T is lost after objects()
class QuerySet:
    def filter(self, **kwargs) -> QuerySet: ...
    async def first(self) -> Optional[T]: ...  # T unresolved → BaseDocument

# Good — T flows through the chain
class QuerySet(Generic[T]):
    def filter(self, **kwargs) -> QuerySet[T]: ...
    async def first(self) -> Optional[T]: ...  # T = User ✓
```

All chainable methods (`filter`, `exclude`, `order_by`, `limit`, `skip`, `only`, `exclude_fields`) must return `QuerySet[T]`, not bare `QuerySet`. The `objects()` classmethod must return `QuerySet[T]`:

```python
@classmethod
def objects(cls: Type[T]) -> QuerySet[T]:
    return QuerySet(document_class=cls, collection_name=cls._get_collection_name())
```

This ensures the full chain resolves correctly:
```
User.objects()           → QuerySet[User]
    .filter(is_active=True) → QuerySet[User]
    .first()             → Optional[User]
```

### How to Verify

If IntelliSense doesn't resolve a method on a document instance, check:
1. Is the class wrapped by a decorator? → Does the decorator return `Type[_D]`?
2. Was the instance returned from a QuerySet? → Is `QuerySet` generic?
3. Is the variable `Optional[T]`? → Is there a narrowing guard (`if not x: raise`)?

### Enforcing with pyright

Run `pyright` in CI to catch type erasure at build time (see Enforcement section).

---

## Code Review Checklist

Before submitting code, verify:

- [ ] All router endpoints are `async def` and return a response
- [ ] All structured inputs/outputs use Pydantic models
- [ ] No raw dict/list returns for structured data
- [ ] No usage of MongoDB `_id` in business logic
- [ ] All methods use keyword-only arguments (`*`) except API endpoints and dunders
- [ ] Error handling uses `Result[T]` for expected errors
- [ ] Units included in attribute names (datetime: `_utc`, duration: `_seconds`, etc.)
- [ ] Nullability is explicit and meaningful (no sentinel values)
- [ ] Optional fields use `T | None`, required fields never return `None`
- [ ] Database method names are explicit (e.g., `get_user_by_user_id`)
- [ ] Primary key IDs are autogenerated with UUID4
- [ ] No direct database access in service layer
- [ ] Status fields use Enums, not raw strings
- [ ] State transitions are centralized
- [ ] No try/catch for control flow (only for true exceptions)
- [ ] Comments explain "why", not "what"
- [ ] No dynamic attribute access (`getattr`, `hasattr`, `setattr`)
- [ ] Imports at top of file (except Modal functions)
- [ ] Error logs use `logger.error()` (not debug/warning) and include traceback + relevant IDs
- [ ] Decorators on document classes preserve concrete types (`Type[_D]`, not `Type[BaseDocument]`)
- [ ] Query builders are `Generic[T]` and chainable methods return `QuerySet[T]`

---

## Enforcement

These rules are **NON-NEGOTIABLE**. Code that violates these standards will be rejected in review.

### Static Type Checking (pyright)

**pyright** is the same engine that powers Pylance (VS Code IntelliSense). Running it in CI catches type erasure, missing methods, and broken generics before code is merged.

```bash
# Install
pip install pyright

# Run against the app
pyright app/

# Strict mode (catches more issues, including untyped parameters)
pyright --pythonversion 3.12 --level basic app/
```

Add to CI alongside existing lint checks:
```bash
black --check --line-length=100 app/
isort --check-only --profile=black app/
flake8 --max-line-length=100 app/
pyright app/
```

pyright catches exactly the issues in Rule 16 — if a decorator erases a type or a QuerySet loses its generic parameter, pyright will flag methods as unresolved.

When in doubt, favor explicitness, type safety, and maintainability over brevity.
