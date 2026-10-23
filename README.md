# Mosaic Hackathon POC Source

Authors: Arulraj S, Mohankumar P, K S Santhosh Kumar
Business unit: Networking - campus and branch

## Run locally

Requires Python 3.10+ and Ollama running on this machine. Install the pinned dependencies:

```sh
python -m pip install -r requirements.txt
ollama pull mistral
python -m mcp_mosaic.demo_app
```

Open http://127.0.0.1:8765 and run the private flow. The demo uses synthetic network data, calls Ollama only on loopback, and does not connect to a Mist tenant or execute the proposed action.

To run the tests:

```sh
python -m pip install -r requirements-dev.txt
python -m pytest mcp_mosaic/test_demo_app.py -q
```

## Scope and limitations

This is a proof of concept. Detection uses a limited set of heuristic patterns and sensitive field names. The demo's short hash-derived tokens are not encryption or production-grade pseudonyms. Production use would require broader detection, high-entropy opaque tokens, verified interception of every model/tool boundary, policy and audit controls, and fail-closed handling.
