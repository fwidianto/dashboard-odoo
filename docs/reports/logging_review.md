# Logging Review Report

**Date:** 2026-06-18
**Purpose:** Review logging strategy and classify logs for permanent retention vs removal

---

## Executive Summary

| Category | Count | Recommendation |
|----------|-------|----------------|
| Keep (INFO) | 45+ | Permanent production logging |
| Keep (WARNING) | 10+ | Production alerts |
| Keep (ERROR) | 10+ | Error tracking |
| Demote to DEBUG | 2 | Detailed tracing |
| Remove | 2 | Debug prints |

**Verdict:** Logging is appropriate. Minor cleanup recommended.

---

## Logging Classification

### Category 1: Keep (Permanent Production Logging)

These logs are essential for production operations:

#### 1.1 Audit Trail Logs

| Log Entry | Level | Purpose | Keep? |
|-----------|-------|---------|-------|
| `INITIALIZE CALLED` | INFO | Startup tracking | ✅ |
| `MODEL FILTERING RESULT` | INFO | Config verification | ✅ |
| `SYNC STATE READ` | INFO | Checkpoint loading | ✅ |
| `CHECKPOINT_SAVING` | INFO | Audit trail | ✅ |
| `CHECKPOINT_SAVED` | INFO | Audit trail | ✅ |
| `INCREMENTAL FILTER GENERATED` | INFO | Operation tracking | ✅ |
| `DOMAIN_DEBUG` | INFO | Debugging info | ✅ |
| `FULL SYNC MODE` | INFO | Operation mode | ✅ |
| `INCREMENTAL SYNC MODE` | INFO | Operation mode | ✅ |
| `Setting result.end_time and last_sync_id` | INFO | Checkpoint tracking | ✅ |

**Recommendation:** KEEP ALL - Essential for troubleshooting

---

#### 1.2 Model Operation Logs

| Log Entry | Level | Purpose | Keep? |
|-----------|-------|---------|-------|
| `INITIALIZING MODEL` | INFO | Progress tracking | ✅ |
| `Fetching fields_get()` | INFO | Metadata discovery | ✅ |
| `fields_get() returned X fields` | INFO | Metadata tracking | ✅ |
| `Running schema validation` | INFO | Validation tracking | ✅ |
| `Creating/Updating table schema` | INFO | Schema ops | ✅ |
| `COMPLETED` | INFO | Completion tracking | ✅ |
| `Starting batch processing` | INFO | Batch start | ✅ |
| `Batch processed` | INFO | Progress tracking | ✅ |
| `BATCH_BOUNDS` | INFO | Batch diagnostics | ✅ |

**Recommendation:** KEEP ALL - User feedback and progress

---

#### 1.3 Error/Warning Logs

| Log Entry | Level | Purpose | Keep? |
|-----------|-------|---------|-------|
| `WRITE_DATE_COMPARISON_ERROR` | ERROR | Type mismatch error | ✅ |
| `RECORD_FALSE_WRITE_DATE` | WARNING | Model-specific issue | ✅ |
| `RECORD_NULL_WRITE_DATE` | WARNING | NULL handling | ✅ |
| `RECORD_BOOL_WRITE_DATE` | WARNING | Type handling | ✅ |
| `RECORD_INVALID_WRITE_DATE` | WARNING | Invalid data | ✅ |
| `SKIPPING_INVALID_ASSIGNMENT` | WARNING | Data validation | ✅ |
| `Some records failed to upsert` | WARNING | Operation feedback | ✅ |
| `No previous sync found` | WARNING | Full sync fallback | ✅ |
| `Fields not in Odoo schema` | WARNING | Schema drift | ✅ |

**Recommendation:** KEEP ALL - Essential for problem diagnosis

---

### Category 2: Demote to DEBUG

These logs provide detailed tracing but are too verbose for INFO level:

#### 2.1 Checkpoint Tracing Logs

| Log Entry | Current Level | Recommended | Reason |
|-----------|--------------|-------------|--------|
| `MAX_WRITE_DATE_FOUND` | INFO | DEBUG | Triggers on every record with new max |
| `MAX_ID_FOR_SAME_DATE` | INFO | DEBUG | Triggers on every record with same date |

**Current behavior:**
```
MAX_WRITE_DATE_FOUND - Triggers potentially thousands of times
MAX_ID_FOR_SAME_DATE - Triggers potentially thousands of times
```

**Recommended change:**
```python
# Change from:
self._logger.info("MAX_WRITE_DATE_FOUND", ...)

# To:
self._logger.debug("MAX_WRITE_DATE_FOUND", ...)
```

**Recommendation:** DEMOTE to DEBUG - Too verbose for production

---

### Category 3: Convert print() to logger

These debug print statements should use proper logging:

| File | Line | Current | Recommended |
|------|------|---------|-------------|
| `src/clients/odoo_client.py` | 617 | `print(f"[DEBUG] read_batched called...")` | `self._logger.debug("Batched read called", ...)` |
| `src/engine/sync_engine.py` | 868 | `print(f"[DEBUG] sync_all called...")` | `self._logger.debug("Sync all called", ...)` |

**Recommendation:** CONVERT to logger - Better log management

---

### Category 4: Remove

None identified.

---

## Log Level Standards

### INFO Level (Keep)

Use for:
- Operation start/completion
- Configuration changes
- Significant milestones
- Checkpoint saves/loads
- Error summaries

### DEBUG Level (Add)

Use for:
- Record-by-record tracing
- Variable state changes
- Loop iterations (except significant ones)
- Detailed diagnostics

### WARNING Level (Keep)

Use for:
- Recoverable issues
- NULL/False value handling
- Missing optional data
- Fallback operations

### ERROR Level (Keep)

Use for:
- Operation failures
- Type mismatches
- Connection issues
- Unrecoverable errors

---

## Recommended Changes

### Immediate (High Priority)

```python
# File: src/engine/sync_engine.py

# Line ~627 - Demote to DEBUG
self._logger.debug(  # Changed from info
    "MAX_WRITE_DATE_FOUND",
    ...
)

# Line ~647 - Demote to DEBUG
self._logger.debug(  # Changed from info
    "MAX_ID_FOR_SAME_DATE",
    ...
)
```

### Short-term (Medium Priority)

```python
# File: src/clients/odoo_client.py
# Line ~617 - Convert to logger

# BEFORE:
print(f"[DEBUG] read_batched called: total_limit={total_limit}, total={total}")

# AFTER:
self._logger.debug(
    "Batched read called",
    model=model,
    total_limit=total_limit,
    total=total,
)
```

```python
# File: src/engine/sync_engine.py
# Line ~868 - Convert to logger

# BEFORE:
print(f"[DEBUG] sync_all called: record_limit={record_limit}")

# AFTER:
self._logger.debug(
    "Sync all called",
    record_limit=record_limit,
)
```

---

## Current vs Recommended Volume

| Level | Current | Recommended | Change |
|-------|---------|-------------|--------|
| INFO | ~50 | ~48 | -2 |
| DEBUG | ~5 | ~10 | +5 |
| WARNING | ~10 | ~10 | 0 |
| ERROR | ~5 | ~5 | 0 |
| print() | 2 | 0 | -2 |

**Summary:**
- Remove 2 `print()` statements
- Demote 2 logs from INFO to DEBUG
- Total: 4 changes

---

## Structured Logging Consistency

### Current State

The codebase uses structured logging with custom event names:

```python
self._logger.info(
    "CHECKPOINT_SAVED",
    model=model_config.odoo_model,
    raw_last_write_date=last_write_date,
    raw_last_id=last_id,
)
```

### Good Examples

```python
# Good: Structured with event name and context
self._logger.info(
    "CHECKPOINT_SAVED",
    model="sale.order",
    raw_last_write_date="2026-06-19 09:52:36",
    raw_last_id=3910,
)

# Good: Error with details
self._logger.error(
    "WRITE_DATE_COMPARISON_ERROR",
    model="stock.quant",
    record_id=123,
    error="' > ' not supported between instances",
)
```

### Recommendations

1. ✅ Keep current structured logging pattern
2. ✅ Use event name as first argument
3. ✅ Include all relevant context
4. ✅ Avoid string interpolation for structured data

---

## Conclusion

**Overall Assessment:** LOGGING IS WELL-STRUCTURED

The logging strategy is appropriate for a production data sync application:

✅ Good use of structured logging
✅ Appropriate log levels
✅ Essential audit trail for checkpoints
✅ Clear error messages with context

**Minor Improvements:**
- Demote 2 verbose logs to DEBUG
- Convert 2 print statements to logger

**Effort to implement:** ~15 minutes
