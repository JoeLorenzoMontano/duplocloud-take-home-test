# Document Processing API

A RAG (Retrieval-Augmented Generation) application that processes documents, stores their embeddings in ChromaDB, and uses Ollama to generate responses to user queries based on the most relevant documents.

## Components

- **FastAPI**: Web server for document processing and querying
- **ChromaDB**: Vector database for storing document embeddings
- **Ollama**: Local LLM service for generating embeddings and responses

## Setup and Usage

### Prerequisites

- Docker and Docker Compose

### Running the Application

#### Option 1: Using docker-compose directly

1. Clone this repository
2. Navigate to the project directory
3. Run:

```bash
docker-compose up -d
```

4. Wait for all services to start (this may take some time as Ollama downloads the necessary models)

#### Option 2: Using the run script

For convenience, a run script is provided that simplifies starting the application with or without GPU support:

```bash
# Run with CPU only
./run.sh

# Run with GPU support
./run.sh --gpu

# Run with custom GPU settings
./run.sh --gpu --gpu-device 0 --gpu-layers 35 --gpu-count 1
```

For all available options, run:

```bash
./run.sh --help
```

### Configuration Options

#### GPU Support

To enable GPU support for Ollama, you can either use the run script as shown above, or set the following environment variables before running docker-compose:

```bash
# Enable GPU support
export OLLAMA_GPU_DEVICES=0        # GPU devices to use (e.g., "0" or "0,1")
export OLLAMA_GPU_LAYERS=35        # Number of layers to offload to GPU (higher = more GPU utilization)
export OLLAMA_GPU_COUNT=1          # Number of GPUs to use
export OLLAMA_GPU_MODE="shared"    # GPU mode ("shared" or "exclusive")

# Then run docker-compose
docker-compose up -d
```

The GPU settings will be ignored if you don't set these variables, allowing the application to run on CPU only.

#### Models

The application uses two different models:
- `MODEL` (default: llama2) - Used for generating responses to queries
- `EMBEDDING_MODEL` (default: all-minilm:l6-v2) - Specialized model for generating embeddings

You can override these defaults by setting environment variables:

```bash
# Use specific models
export MODEL=mistral               # For generating responses
export EMBEDDING_MODEL=nomic-embed-text  # For generating embeddings

# Then run docker-compose
docker-compose up -d
```

#### Web Search API Integration

To enable the web search feature with Serper.dev API:

```bash
# Set the Serper API key
export SERPER_API_KEY=your_serper_api_key_here

# Then run docker-compose
docker-compose up -d
```

#### Web Search Integration

The application includes an optional web search feature that can augment the RAG results with information from the internet. This is particularly useful for queries that may require up-to-date information not available in your local document collection.

To use the web search feature:

1. Set the Serper API key as an environment variable:

```bash
# Add to your .env file or set directly
export SERPER_API_KEY=your_serper_api_key_here
```

2. Enable web search in your queries:

```bash
# Enable web search with 5 results
curl -X GET "http://localhost:8000/query?query=Your%20question&web_search=true&web_results_count=5"
```

3. In the UI, simply check the "Include Web Search Results" checkbox when making a query.

The web search results will be integrated into the context provided to the LLM, and will be displayed as additional sources in the UI.

Note: Web search requires an active internet connection and uses the Serper.dev API, which may have usage limits depending on your subscription.

#### Document Chunking

The application supports document chunking for improved retrieval performance. Chunking divides large documents into smaller pieces with some overlap, which helps make embeddings more focused and retrieval more accurate.

You can configure chunking with the following options:

```bash
# Using the run script
./run.sh --chunk-size 1500 --chunk-overlap 150 --min-chunk-size 300
./run.sh --no-chunking  # To disable chunking

# Or with environment variables
export ENABLE_CHUNKING=true     # Enable/disable chunking (default: true)
export MAX_CHUNK_SIZE=1000      # Maximum characters per chunk (default: 1000)
export MIN_CHUNK_SIZE=200       # Minimum size for a chunk (default: 200)
export CHUNK_OVERLAP=100        # Overlap between chunks (default: 100)

# Then run docker-compose
docker-compose up -d
```

You can also override chunking settings when processing documents through the API:

```bash
# Override chunking settings for a specific processing run
curl -X POST "http://localhost:8000/process?chunk_size=1500&min_size=300&overlap=150"

# Disable chunking for a specific run
curl -X POST "http://localhost:8000/process?enable_chunking=false"
```

### API Endpoints

- **POST /process**: Processes all documents in the `rag-documents` directory and stores their embeddings in ChromaDB
  - Optional query parameters:
    - `chunk_size`: Override max chunk size
    - `min_size`: Override min chunk size
    - `overlap`: Override chunk overlap
    - `enable_chunking`: Override chunking enabled setting (true/false)
  
- **GET /query?query=YOUR_QUERY**: Returns a response based on the most relevant documents matching your query
  - Optional query parameters:
    - `n_results`: Number of results to return (default: 3)
    - `combine_chunks`: Whether to combine chunks from the same document (default: true)
    - `web_search`: Whether to augment with web search results (default: false)
    - `web_results_count`: Number of web search results to include (default: 5)

- **GET /health**: Returns detailed health status of all services and components

- **POST /test-embedding?text=YOUR_TEXT**: Tests the embedding functionality with custom text (useful for debugging)

### Example Usage

1. Once all services are up, process the documents:

```bash
curl -X POST http://localhost:8000/process
```

2. Query the system:

```bash
curl -X GET "http://localhost:8000/query?query=What%20are%20the%20tenant%20configuration%20settings?"
```

## Directory Structure

- `/app`: Contains the FastAPI application code
- `/rag-documents`: Contains markdown documents to be processed
- `/docker-compose.yml`: Docker Compose configuration for all services

## Troubleshooting

- If you encounter issues with the Ollama service, check the logs with `docker logs ollama-server`
- If you encounter issues with ChromaDB, check the logs with `docker logs chromadb`
- If you need to reset the system, you can run `docker-compose down -v` to remove all volumes and containers, then `docker-compose up -d` to start fresh

### Common Issues

#### Embedding API Response Format

The Ollama embedding API can return responses in different formats depending on the model:
- Some models return an `embedding` field with the vector directly
- Others (like all-minilm:l6-v2) return an `embeddings` field with an array of vectors

The application now handles both formats automatically. You can test embedding generation with:

```bash
# Test with the /test-embedding endpoint
curl -X POST "http://localhost:8000/test-embedding?text=This%20is%20a%20test"

# Or check the health endpoint for embedded status
curl http://localhost:8000/health
```

If you're experiencing embedding issues, you can also check Ollama's embed API directly:

```bash
# Direct test of the Ollama embedding API
curl -X POST http://localhost:11434/api/embed -d '{"model":"all-minilm:l6-v2","input":"test"}'
```

#### ChromaDB Connection Issues

If you encounter connection issues with ChromaDB, try:
1. Checking the ChromaDB logs: `docker logs chromadb`
2. Ensuring the correct ports are mapped in docker-compose.yml
3. Verifying there are no version conflicts with NumPy (should be <2.0.0)

#### GPU Support Compatibility

If GPU acceleration isn't working:
1. Verify your system has NVIDIA drivers installed
2. Check that the Docker NVIDIA runtime is installed
3. Ensure your GPU is compatible with the layers setting (try reducing `--gpu-layers`)

#### Windows WSL2 GPU Support Considerations

If you're using Windows with Docker Desktop and WSL2, there are additional requirements for GPU support:

1. **NVIDIA GPU Driver for WSL**: You need to install the specific NVIDIA driver that supports WSL2 GPU passthrough
   - Download from [NVIDIA's WSL-compatible driver page](https://developer.nvidia.com/cuda/wsl)
   - Follow NVIDIA's installation instructions for WSL2 support

2. **WSL2 Configuration**: Ensure your WSL2 distribution is properly configured to access the GPU
   ```bash
   # Check if NVIDIA drivers are accessible from within WSL2
   nvidia-smi
   ```

3. **Potential Limitations**: Not all GPU features may be available through WSL2
   - Performance might be lower than on native Linux
   - Some CUDA features might not work as expected
   - Newer GPUs typically have better support

4. **Troubleshooting WSL2 GPU Issues**:
   - Ensure your Windows host has the latest Windows Updates
   - Update Docker Desktop to the latest version
   - Make sure WSL2 is set as the default WSL version: `wsl --set-default-version 2`
   - Check GPU is visible inside WSL2: `wsl --distribution <your-distro> --exec nvidia-smi`