# GPT-Agent: A simple agent using OpenAI APIs

## Environement (.env)
Put the required API keys in the file .env (VAR=VALUE, one per line).

Required:
- `OPENAI_API_KEY`: OpenAI API key
- `OPENAI_ORG_ID`: OpenAI organization ID

Optional:
- `SERPAPI_KEY`: SerpAPI key
- `GOOGLE_API_KEY`: Google API key
- `GOOGLE_SEARCH_ID`: Google search ID

## Usage

### Using docker compose
```bash
docker-compose build
docker-compose up
```

### Using docker
```bash
docker build -t gpt-agent .
docker run -p 8080:8080 -v $(pwd)/results:/project -it gpt-agent
```

### Run locally
Note that running the agent outside of a container is not recommended

Install the dependencies using pip:
```bash
pip install -r requirements.txt
```

```bash
python3 app/agent.py
```

