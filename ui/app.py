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
    enhance_chunks = request.form.get('enhance_chunks')
    
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
    if enhance_chunks is not None:
        params['enhance_chunks'] = enhance_chunks.lower() == 'true'
    
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
    web_search = data.get('web_search', None)  # None means auto-classify
    web_results_count = data.get('web_results_count', 5)
    explain_classification = data.get('explain_classification', False)
    
    if not query_text:
        return jsonify({"status": "error", "message": "Query text is required"})
    
    try:
        # Call the API
        response = requests.get(
            f"{API_URL}/query", 
            params={
                'query': query_text,
                'n_results': n_results,
                'combine_chunks': combine_chunks,
                'web_search': web_search,
                'web_results_count': web_results_count,
                'explain_classification': explain_classification
            },
            timeout=None
        )
        return jsonify(response.json())
    except Exception as e:
        logging.error(f"Error querying documents: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/systeminfo', methods=['GET'])
def systeminfo_page():
    """Render the system information page"""
    return render_template('systeminfo.html')

@app.route('/api/chroma-info', methods=['GET'])
def chroma_info():
    """Get information about ChromaDB"""
    try:
        # Check collection status
        response = requests.get(f"{API_URL}/health", timeout=10)
        health_data = response.json()
        
        # Extract ChromaDB information
        chroma_info = {
            "status": "success",
            "server_version": health_data.get("chroma", "unknown"),
            "api_status": health_data.get("api", "unknown"),
            "document_count": 0,
            "collection_count": 0
        }
        
        # Check collection information
        if "collection" in health_data and health_data["collection"]["status"] == "healthy":
            chroma_info["document_count"] = health_data["collection"]["document_count"]
            chroma_info["collection_count"] = 1  # We only have one collection in this app
            
        return jsonify(chroma_info)
    except Exception as e:
        logging.error(f"Error getting ChromaDB info: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/terms', methods=['GET'])
def get_terms():
    """Get classification terms from the API"""
    try:
        response = requests.get(f"{API_URL}/terms", timeout=10)
        return jsonify(response.json())
    except Exception as e:
        logging.error(f"Error getting terms: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/refresh-terms', methods=['POST'])
def refresh_terms():
    """Refresh classification terms from the API"""
    try:
        response = requests.post(f"{API_URL}/refresh-terms", timeout=20)
        return jsonify(response.json())
    except Exception as e:
        logging.error(f"Error refreshing terms: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/health', methods=['GET'])
def api_health():
    """Get full health status from the API"""
    try:
        response = requests.get(f"{API_URL}/health", timeout=10)
        return jsonify({"api": response.json()})
    except Exception as e:
        logging.error(f"Error getting health status: {e}")
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)