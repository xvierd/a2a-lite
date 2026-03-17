# File Agent - Google A2A SDK (Java)

Multi-skill file handling agent demonstrating the official Google A2A SDK approach with Javalin web framework.

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
| `/.well-known/agent.json` | GET | Agent card (A2A discovery) |
| `/` | POST | A2A message endpoint |

## Usage Examples

### 1. Analyze Text Content

```bash
curl -X POST http://localhost:8789/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [
          {
            "type": "text",
            "text": "{\"skill\": \"analyze\", \"params\": {\"content\": \"Hello world! This is a test.\"}}"
          }
        ]
      }
    }
  }'
```

Response:
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

```bash
# First, base64 encode your file
FILE_CONTENT=$(base64 -i sample.txt)

curl -X POST http://localhost:8789/ \
  -H "Content-Type: application/json" \
  -d "{
    \"jsonrpc\": \"2.0\",
    \"id\": \"1\",
    \"method\": \"message/send\",
    \"params\": {
      \"message\": {
        \"role\": \"user\",
        \"parts\": [
          {
            \"type\": \"text\",
            \"text\": \"{\\\"skill\\\": \\\"analyze\\\", \\\"params\\\": {}}\"
          },
          {
            \"type\": \"file\",
            \"file\": {
              \"name\": \"sample.txt\",
              \"mimeType\": \"text/plain\",
              \"data\": \"$FILE_CONTENT\"
            }
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
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [
          {
            "type": "text",
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
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [
          {
            "type": "text",
            "text": "{\"skill\": \"generate_report\", \"params\": {\"title\": \"Sales Report\", \"format\": \"markdown\", \"data\": {\"total_sales\": 15000, \"orders\": 230, \"avg_order\": 65.22}}}"
          }
        ]
      }
    }
  }'
```

Response:
```json
{
  "filename": "sales_report_20240115_103000.md",
  "title": "Sales Report",
  "format": "markdown",
  "size_bytes": 245,
  "data_points": 3,
  "file": {
    "name": "sales_report_20240115_103000.md",
    "mimeType": "text/markdown",
    "data": "..."
  }
}
```

## Agent Card

Access the agent card at: `http://localhost:8789/.well-known/agent.json`

The agent card includes:
- Agent metadata (name, description, version)
- Capabilities including file handling support
- Skill definitions with input/output schemas
- Supported MIME types and max file size

## Comparison with A2A Lite

| Aspect | Google A2A SDK | A2A Lite |
|--------|---------------|----------|
| Lines of Code | ~780 | ~150 |
| Files | 3 | 1 |
| Manual JSON-RPC handling | Yes | No |
| Manual agent card | Yes | Auto-generated |
| Manual routing | Yes | Auto-routed |
| Builder pattern | No | Yes |

See `../03_file_handling_lite/` for the simplified A2A Lite version.
