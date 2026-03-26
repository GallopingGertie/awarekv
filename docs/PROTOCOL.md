# DAKV Protocol Specification

## Binary Protocol

### Frame Structure

```
+--------+----------+-------------+--------------+--------+---------+
| Magic  | Version  | Header Len  | Payload Len  | Header | Payload |
+--------+----------+-------------+--------------+--------+---------+
| 4 bytes| 2 bytes  | 4 bytes     | 4 bytes      | N bytes| M bytes |
+--------+----------+-------------+--------------+--------+---------+
```

- **Magic**: `DAKV` (0x44414B56)
- **Version**: Protocol version (currently 1)
- **Header Len**: Length of JSON header
- **Payload Len**: Length of payload data
- **Header**: JSON-encoded metadata
- **Payload**: Binary data

### Header Fields

```json
{
  "op": "GET_CRITICAL | GET_REFINEMENT | PUT_CRITICAL | PUT_REFINEMENT | DELETE | RESPONSE | ERROR",
  "request_id": "string",
  "object_id": "string",
  "tier": "T1 | T2",
  "codec": "fp16_raw | int8_symm",
  "checksum": "sha256_hex",
  "deadline_ms": 500
}
```

## Operations

### GET_CRITICAL
Request critical KV blob from storage.

**Request:**
- op: GET_CRITICAL
- object_id: Object identifier
- tier: Storage tier
- deadline_ms: Maximum wait time

**Response:**
- op: RESPONSE
- payload: Encoded KV data

### GET_REFINEMENT
Request refinement KV blob (non-blocking, droppable).

**Request:**
- op: GET_REFINEMENT
- object_id: Object identifier

**Response:**
- op: RESPONSE
- payload: Encoded KV data (or timeout)

### PUT_CRITICAL / PUT_REFINEMENT
Store KV blob to storage.

**Request:**
- op: PUT_CRITICAL or PUT_REFINEMENT
- object_id: Object identifier
- codec: Encoding used
- checksum: SHA256 checksum
- payload: Encoded KV data

**Response:**
- op: RESPONSE
- payload: "OK"

## Error Handling

When an operation fails, server returns:

**Error Response:**
- op: ERROR
- payload: Error message (UTF-8)

## Manifest API (HTTP/JSON)

### Query Manifest
```
POST /manifest/query
{
  "prefix_key": "sha256_hash",
  "request_id": "req_123",
  "need_refinement": true
}

Response:
{
  "hit": true,
  "manifest": { ... },
  "tier": "T2"
}
```

### Put Manifest
```
POST /manifest/put
{
  "prefix_key": "...",
  "matched_tokens": 256,
  "critical_object_id": "...",
  "refinement_object_id": "...",
  ...
}
```

### Get Stats
```
GET /manifest/stats

Response:
{
  "total_manifests": 100,
  "total_objects": 200,
  "total_bytes": 1073741824
}
```
