from flask import Flask, render_template, request, jsonify
import requests
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s %(levelname)s: %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')

app = Flask(__name__)

# Get API URL from environment variable or use default
API_URL = os.getenv("API_URL", "http://api:8000")
logging.info(f"Using API URL: {API_URL}")

@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')

@app.route('/health')
def health():
    """Check health of both UI and API"""
    ui_health = {"status": "healthy"}
    
    # Check API health
    try:
        api_response = requests.get(f"{API_URL}/health", timeout=5)
        api_health = api_response.json()
    except Exception as e:
        logging.error(f"Error connecting to API: {e}")
        api_health = {"status": "error", "message": str(e)}
    
    return jsonify({
        "ui": ui_health,
        "api": api_health
    })

@app.route('/process', methods=['GET'])
def process_page():
    """Render the document processing page"""
    return render_template('process.html')

@app.route('/process-documents', methods=['POST'])
def process_documents():
    """Proxy for the document processing API endpoint"""
    # Get chunking parameters from the form
    chunk_size = request.form.get('chunk_size')
    min_size = request.form.get('min_size')
    overlap = request.form.get('overlap')
    enable_chunking = request.form.get('enable_chunking')
    
    # Build query parameters
    params = {}
    if chunk_size and chunk_size.isdigit():
        params['chunk_size'] = int(chunk_size)
    if min_size and min_size.isdigit():
        params['min_size'] = int(min_size)
    if overlap and overlap.isdigit():
        params['overlap'] = int(overlap)
    if enable_chunking is not None:
        params['enable_chunking'] = enable_chunking.lower() == 'true'
    
    try:
        # Call the API
        response = requests.post(f"{API_URL}/process", params=params, timeout=60)
        return jsonify(response.json())
    except Exception as e:
        logging.error(f"Error processing documents: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/query', methods=['GET'])
def query_page():
    """Render the query page"""
    return render_template('query.html')

@app.route('/query-documents', methods=['POST'])
def query_documents():
    """Proxy for the document query API endpoint"""
    data = request.get_json()
    query_text = data.get('query', '')
    n_results = data.get('n_results', 3)
    combine_chunks = data.get('combine_chunks', True)
    
    if not query_text:
        return jsonify({"status": "error", "message": "Query text is required"})
    
    try:
        # Call the API
        response = requests.get(
            f"{API_URL}/query", 
            params={
                'query': query_text,
                'n_results': n_results,
                'combine_chunks': combine_chunks
            },
            timeout=None
        )
        return jsonify(response.json())
    except Exception as e:
        logging.error(f"Error querying documents: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/test-embedding', methods=['GET'])
def test_embedding_page():
    """Render the test embedding page"""
    return render_template('test_embedding.html')

@app.route('/test-embedding', methods=['POST'])
def test_embedding():
    """Proxy for the test embedding API endpoint"""
    data = request.get_json()
    text = data.get('text', 'This is a test of the embedding functionality')
    
    try:
        # Call the API
        response = requests.post(
            f"{API_URL}/test-embedding", 
            params={'text': text},
            timeout=10
        )
        return jsonify(response.json())
    except Exception as e:
        logging.error(f"Error testing embedding: {e}")
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)