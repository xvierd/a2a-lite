# File Agent - A2A v1.0 from scratch (Java)

Multi-skill file handling agent implementing the A2A protocol v1.0 wire format by hand with Javalin + Jackson — **no SDK**. For the official Java SDK approach see `packages/java`.

## Overview

This example shows a complete file handling agent with:
- **analyze**: Get text statistics (word count, line count, char count, average word length)
- **convert_to_upper**: Convert text content to uppercase
- **generate_report**: Generate formatted reports in JSON, Markdown, or Text formats

File Support:
- Direct text content
- Base64-encoded file uploads
- Supported MIME types: `text/plain`, `text/markdown`, `application/json`, `text/csv`
- Maximum file size: 10MB

## Project Structure

```
03_file_handling_google/
├── pom.xml
├── README.md
└── src/main/java/com/example/fileagent/
    ├── FileAgent.java      # Main server and agent card setup (~280 lines)
    ├── FileSkill.java      # Business logic for file operations (~260 lines)
    └── MessageHandler.java # A2A protocol handling (~240 lines)
```

**Total: ~780 lines of code**

## Prerequisites

- Java 17 or higher
- Maven 3.6+

## Build

```bash
cd 03_file_handling_google
mvn clean package
```

## Run

```bash
# Using Maven
mvn exec:java

# Or run the JAR directly
java -jar target/file-agent-google-1.0.0.jar
```

The agent will start on `http://localhost:8789`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/.well-known/agent-card.json` | GET | Agent card (A2A v1.0 discovery) |
| `/` | POST | A2A JSON-RPC endpoint (`SendMessage`) |

All JSON-RPC responses include the `A2A-Version: 1.0` header.

## Usage Examples

### 1. Analyze Text Content

```bash
curl -X POST http://localhost:8789/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "SendMessage",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "m1",
        "parts": [
          {
            "text": "{\"skill\": \"analyze\", \"params\": {\"content\": \"Hello world! This is a test.\"}}"
          }
        ]
      }
    }
  }'
```

Response (`result.message.parts[0].text` carries the JSON result):
```json
{
  "word_count": 6,
  "line_count": 1,
  "character_count": 30,
  "average_word_length": 4.33,
  "analyzed_at": "2024-01-15T10:30:00"
}
```

### 2. Analyze File Upload

In A2A v1.0 an inline base64 file is a part with `raw` / `mediaType` / `filename` (no `kind` or `type` field):

```bash
# First, base64 encode your file
FILE_CONTENT=$(base64 -i sample.txt)

curl -X POST http://localhost:8789/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d "{
    \"jsonrpc\": \"2.0\",
    \"id\": \"1\",
    \"method\": \"SendMessage\",
    \"params\": {
      \"message\": {
        \"role\": \"ROLE_USER\",
        \"messageId\": \"m2\",
        \"parts\": [
          {
            \"text\": \"{\\\"skill\\\": \\\"analyze\\\", \\\"params\\\": {}}\"
          },
          {
            \"raw\": \"$FILE_CONTENT\",
            \"mediaType\": \"text/plain\",
            \"filename\": \"sample.txt\"
          }
        ]
      }
    }
  }"
```

### 3. Convert to Uppercase

```bash
curl -X POST http://localhost:8789/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "SendMessage",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "m3",
        "parts": [
          {
            "text": "{\"skill\": \"convert_to_upper\", \"params\": {\"content\": \"hello world\"}}"
          }
        ]
      }
    }
  }'
```

Response:
```json
{
  "original_length": 11,
  "converted_length": 11,
  "converted_text": "HELLO WORLD",
  "changes_made": true
}
```

### 4. Generate Report

```bash
curl -X POST http://localhost:8789/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "SendMessage",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "m4",
        "parts": [
          {
            "text": "{\"skill\": \"generate_report\", \"params\": {\"title\": \"Sales Report\", \"format\": \"markdown\", \"data\": {\"total_sales\": 15000, \"orders\": 230, \"avg_order\": 65.22}}}"
          }
        ]
      }
    }
  }'
```

Response (summary in the text part; the generated file comes back as a second part with `raw`/`mediaType`/`filename`):
```json
{
  "filename": "sales_report_20240115_103000.md",
  "title": "Sales Report",
  "format": "markdown",
  "size_bytes": 245,
  "data_points": 3
}
```

## Agent Card

Access the agent card at: `http://localhost:8789/.well-known/agent-card.json`

The v1.0 agent card includes:
- Agent metadata (name, description, version)
- `supportedInterfaces` with the endpoint URL, `protocolBinding: JSONRPC` and `protocolVersion: 1.0`
- Capabilities including file handling support
- Skill definitions with `id`, `name`, `description`, `tags` and input schemas
- Supported MIME types and max file size

## Comparison with A2A Lite

| Aspect | From scratch (this example) | A2A Lite |
|--------|----------------------------|----------|
| Lines of Code | ~780 | ~150 |
| Files | 3 | 1 |
| Manual JSON-RPC handling | Yes | No |
| Manual agent card | Yes | Auto-generated |
| Manual routing | Yes | Auto-routed |
| Builder pattern | No | Yes |

See `../03_file_handling_lite/` for the simplified A2A Lite version.
