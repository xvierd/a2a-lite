# File Handling - A2A Lite (Python)

> **File upload and processing agent using A2A Lite.**

This example demonstrates how to handle file uploads, process binary data, and return file responses using A2A Lite's `FilePart` abstraction.

---

## 📁 Files Overview

| File | Purpose | Lines |
|------|---------|-------|
| `agent.py` | File processing agent | ~50 |
| `requirements.txt` | Dependencies | ~2 |
| `test_file/sample.txt` | Sample file for testing | - |

**Total: ~52 lines**

---

## 🚀 Quick Start

```bash
cd python/03_file_handling_lite
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python agent.py
```

---

## 🧪 Testing

### Upload and Analyze a File

```bash
# Create a test file
echo "Hello, this is a test file for A2A protocol." > test_file.txt

# Upload via curl (base64 encoded)
curl -X POST http://localhost:8789/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendMessage",
    "id": "1",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "parts": [
          {
            "raw": "SGVsbG8sIHRoaXMgaXMgYSB0ZXN0IGZpbGUgZm9yIEEyQSBwcm90b2NvbC4=",
            "filename": "test_file.txt",
            "mediaType": "text/plain"
          }
        ],
        "messageId": "msg-1"
      }
    }
  }'

# Expected: File analysis with size, word count, etc.
```

---

## 📖 Key Concepts

### FilePart Abstraction

A2A Lite provides `FilePart` to handle file uploads:

```python
from a2a_lite import FilePart

@agent.skill("analyze")
async def analyze(file: FilePart) -> dict:
    # Read as text
    content = await file.read_text()
    
    # Or as bytes
    data = await file.read_bytes()
    
    return {
        "filename": file.name,
        "size": len(data),
        "content": content[:100]  # First 100 chars
    }
```

### Creating File Responses

```python
from a2a_lite import FilePart

@agent.skill("generate")
async def generate() -> FilePart:
    content = b"Generated file content..."
    return FilePart(name="output.txt", data=content)
```

---

## 🔍 Comparison with Google SDK

| Task | Google SDK | A2A Lite |
|------|------------|----------|
| File Parsing | Manual base64 decode | `file.read_*()` methods |
| MIME Type Handling | Manual | Auto-detected |
| File Response | Manual part construction | Return `FilePart` directly |
| Validation | Manual | Built-in |

See [Google SDK version](../03_file_handling_google/) for comparison.
