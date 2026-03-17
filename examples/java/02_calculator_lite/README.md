# Calculator Agent - A2A Lite (Java)

Multi-skill calculator using the **real A2A Lite library**.

## Building

```bash
cd ../../../packages/java
./gradlew publishToMavenLocal

cd examples/java/02_calculator_lite
./gradlew build
```

## Running

```bash
./gradlew run
```

## API

### Skills

- `add` - Add two numbers (params: a, b)
- `subtract` - Subtract two numbers (params: a, b)
- `multiply` - Multiply two numbers (params: a, b)
- `divide` - Divide two numbers (params: a, b)
- `power` - Calculate power (params: base, exponent)

### Example Request

```bash
curl -X POST http://localhost:8788/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "parts": [{"type": "text", "text": "{\"skill\": \"add\", \"params\": {\"a\": 10, \"b\": 5}}"}]
      }
    }
  }'
```
