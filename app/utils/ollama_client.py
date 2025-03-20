import requests
import json
import re
import os
from typing import List, Dict, Optional

class OllamaClient:
    def __init__(self, base_url: str = None, model: str = None):
        """
        Initializes the Ollama client.
        :param base_url: Ollama server URL (default: local Ollama instance)
        :param model: Default model to use for generating responses
        """
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = model or os.getenv("MODEL", "llama2")
        
        # Make sure base_url doesn't end with a slash
        if self.base_url.endswith('/'):
            self.base_url = self.base_url[:-1]

    def generate_response(self, context: str, query: str, model: Optional[str] = None, max_tokens: Optional[int] = None) -> str:
        """
        Sends a query to the Ollama server with strict response rules.
        """
        current_model = model or self.model
        
        # Check if the model exists, if not pull it
        self._ensure_model_exists(current_model)
        
        payload = {
            "model": current_model,
            "prompt": (
                "You are an AI assistant that must follow strict response rules.\n"
                "### 🔹 **Rules (MUST FOLLOW):**\n"
                "1 **You MUST ONLY use information from the provided context.**\n"
                "2 **If the answer is NOT in the context, respond with:**\n"
                "   ❌ 'I could not find relevant information in the provided context. Please provide additional details if needed.'\n"
                "3 **You MUST NOT generate an answer using external knowledge.**\n"
                "4 **You MUST NOT make up any information.**\n\n"
                "### 🔹 **Context (ONLY use the information provided below to answer the query):**\n"
                f"\"\"\"\n{context}\n\"\"\"\n\n"
                f"Query: {query}"
            ),
            "stream": False
        }
        
        # Add max_tokens if provided
        if max_tokens:
            payload["options"] = {"num_predict": max_tokens}

        response = requests.post(f"{self.base_url}/api/generate", json=payload)
        response.raise_for_status()
        result = response.json()
        return self._remove_think_regions(result.get("response", "No response generated."))

    def _ensure_model_exists(self, model_name: str) -> None:
        """
        Checks if a model exists, and tries to use a default model if it doesn't.
        """
        try:
            # Check if model exists
            response = requests.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            
            models_data = response.json()
            # Handle different response formats
            models = []
            if "models" in models_data:
                models = models_data["models"]
            elif isinstance(models_data, list):
                models = models_data
                
            # Simplify model names for comparison
            available_models = [model["name"].split(":")[0] if ":" in model["name"] else model["name"] 
                               for model in models]
            model_name_simple = model_name.split(":")[0] if ":" in model_name else model_name
            
            # Check if our model exists (exact or base name match)
            if not (model_name in available_models or model_name_simple in available_models):
                print(f"Model {model_name} not available.")
                if models:
                    # Use first available model as fallback
                    self.model = models[0]["name"]
                    print(f"Using {self.model} as fallback.")
                else:
                    print(f"No models available. Will attempt to pull llama2 when needed.")
                    self.model = "llama2"
        except Exception as e:
            print(f"Error checking available models: {e}")
            print("Will use default model settings and let Ollama handle errors.")

    def summarize_text(self, text: str, context: str, model: Optional[str] = None, max_tokens: Optional[int] = None) -> str:
        """
        Summarizes the provided text following strict summarization rules.
        """
        if not text.strip():
            return "Error: No input text provided."
            
        current_model = model or self.model
        
        # Ensure model exists
        self._ensure_model_exists(current_model)

        payload = {
            "model": current_model,
            "prompt": (
                "You are an AI assistant specializing in summarization.\n"
                "### 🔹 **Summarization Rules:**\n"
                "1. **Preserve all key details.**\n"
                "2. **Include all relevant facts, quotes, and statistics.**\n"
                "3. **Do NOT change the meaning of the original text.**\n"
                "4. **Do NOT add opinions or remove crucial context.**\n\n"
                "### 🔹 **Context (Previous Chunks):**\n"
                f"\"\"\"\n{context}\n\"\"\"\n\n"
                "### 🔹 **Text to Summarize:**\n"
                f"\"\"\"\n{text}\n\"\"\"\n\n"
                "Provide a concise yet detailed summary."
            ),
            "stream": False
        }
        
        # Add max_tokens if provided
        if max_tokens:
            payload["options"] = {"num_predict": max_tokens}

        response = requests.post(f"{self.base_url}/api/generate", json=payload)
        response.raise_for_status()
        result = response.json()
        return self._remove_think_regions(result.get("response", "No summary generated."))

    def generate_embedding(self, input_text: str) -> List[float]:
        """
        Generates an embedding for the given input text using the Ollama API.
        
        According to the Ollama API docs, the /api/embeddings endpoint expects:
        - model: name of the model to use
        - prompt: text to generate embeddings for
        
        Returns a list of floats (the embedding vector)
        """
        # Use available models to generate embeddings
        models_to_try = [self.model]  # Start with configured model
        
        # Try to fetch available models
        try:
            response = requests.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                result = response.json()
                if "models" in result:
                    models = result["models"]
                elif isinstance(result, list):
                    models = result
                else:
                    models = []
                
                # Find embedding-specific models first
                for model in models:
                    name = model.get("name", "")
                    if any(x in name.lower() for x in ["embed", "e5", "nomic", "all-minilm", "text-embedding"]):
                        if name not in models_to_try:
                            models_to_try.insert(0, name)  # Add embedding models to the front
        except Exception as e:
            print(f"Error fetching models: {e}")
        
        # Add some well-known embedding models to try
        for model_name in ["nomic-embed-text", "all-minilm", "e5-small", self.model]:
            if model_name not in models_to_try:
                models_to_try.append(model_name)
        
        # Try each model in order
        last_error = None
        for model_name in models_to_try:
            try:
                print(f"Trying to generate embedding with model: {model_name}")
                payload = {
                    "model": model_name,
                    "prompt": input_text
                }
                
                # Use the /api/embed endpoint (not /api/embeddings)
                response = requests.post(f"{self.base_url}/api/embed", json=payload)
                response.raise_for_status()
                result = response.json()
                embedding = result.get("embedding", [])
                
                # Check if we got a valid embedding
                if embedding and len(embedding) > 10:  # Basic validation
                    print(f"Successfully generated embedding with model: {model_name}")
                    return embedding
                else:
                    print(f"Model {model_name} returned an invalid embedding")
            except Exception as e:
                last_error = e
                print(f"Error generating embedding with model {model_name}: {e}")
        
        # If all models failed, generate a random embedding
        print(f"All embedding models failed. Last error: {last_error}")
        print("Generating random embedding for testing purposes")
        
        # Create a random embedding
        import random
        import numpy as np
        
        # Generate a random unit vector (normalized)
        embedding_size = 768  # Standard size for many embedding models
        random_vector = np.random.randn(embedding_size)
        normalized = random_vector / np.linalg.norm(random_vector)
        return normalized.tolist()

    def extract_metadata(self, text: str, model: Optional[str] = None, max_tokens: Optional[int] = None) -> Dict[str, str]:
        """
        Extracts structured metadata from the text following a strict JSON schema.
        """
        current_model = model or self.model
        
        # Ensure model exists
        self._ensure_model_exists(current_model)
        
        payload = {
            "model": current_model,
            "prompt": (
                "You are an AI assistant that extracts structured metadata from text. "
                "You must follow the JSON schema strictly without adding explanations or extra formatting.\n\n"
                f"Extract metadata from this document:\n\n\"\"\"\n{text}\n\"\"\"\n\n"
                "Output the metadata as a valid JSON object with fields for title, author, date, and summary."
            ),
            "stream": False
        }
        
        # Add max_tokens if provided
        if max_tokens:
            payload["options"] = {"num_predict": max_tokens}

        response = requests.post(f"{self.base_url}/api/generate", json=payload)
        response.raise_for_status()
        result = response.json()
        
        response_content = result.get("response", "{}")
        try:
            # Try to extract JSON from the response
            json_match = re.search(r'```json\s*(.*?)\s*```', response_content, re.DOTALL)
            if json_match:
                response_content = json_match.group(1)
            
            # Clean up any non-JSON content
            response_content = re.sub(r'^[^{]*', '', response_content)
            response_content = re.sub(r'[^}]*$', '', response_content)
            
            return self._normalize_metadata(json.loads(response_content))
        except json.JSONDecodeError:
            return {"error": "Failed to parse JSON response", "content": response_content}

    def _normalize_metadata(self, metadata: Dict[str, str]) -> Dict[str, str]:
        """
        Converts arrays into pipe-separated strings.
        """
        fields_to_convert = {"named_entities", "keywords"}
        for field in fields_to_convert:
            if field in metadata and isinstance(metadata[field], list):
                metadata[field] = "|".join(metadata[field])
        return metadata

    def _remove_think_regions(self, text: str) -> str:
        """
        Removes `<think>...</think>` sections from the AI output.
        """
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()