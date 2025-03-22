"""
Query processing service.

This module handles query processing, document retrieval, and response generation.
"""

import logging
from typing import Dict, List, Any, Tuple, Optional

from utils.ollama_client import OllamaClient
from utils.query_classifier import QueryClassifier
from utils.web_search import WebSearchClient
from services.database_service import DatabaseService

class QueryService:
    """Service for processing queries and generating responses."""
    
    def __init__(self, 
                db_service: DatabaseService,
                ollama_client: OllamaClient,
                query_classifier: QueryClassifier,
                web_search_client: Optional[WebSearchClient] = None):
        """
        Initialize the query processing service.
        
        Args:
            db_service: Database service for retrieval
            ollama_client: Ollama client for embeddings and responses
            query_classifier: Query classifier for routing
            web_search_client: Optional web search client
        """
        self.db_service = db_service
        self.ollama_client = ollama_client
        self.query_classifier = query_classifier
        self.web_search_client = web_search_client
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
    
    def process_query(self, 
                     query: str, 
                     n_results: int = 3, 
                     combine_chunks: bool = True,
                     web_search: Optional[bool] = None,
                     web_results_count: int = 5,
                     explain_classification: bool = False) -> Dict[str, Any]:
        """
        Process a query and generate a response.
        
        Args:
            query: The user's query
            n_results: Number of results to return
            combine_chunks: Whether to combine chunks from the same document
            web_search: Whether to use web search (None for auto)
            web_results_count: Number of web search results to include
            explain_classification: Whether to include classification explanation
            
        Returns:
            Dictionary with query response and sources
        """
        try:
            # Check if ChromaDB has any documents at all
            doc_count = self.db_service.get_document_count()
            if doc_count == 0:
                return {
                    "query": query,
                    "response": "No documents have been processed yet. Please use the /process endpoint first.",
                    "sources": {"documents": [], "ids": [], "metadatas": []},
                    "status": "error",
                    "error": "Empty collection"
                }
                
            # Generate embedding for the query using Ollama
            query_embedding = self.ollama_client.generate_embedding(query)
            
            # Log the embedding dimension for debugging
            self.logger.info(f"Generated query embedding with dimension: {len(query_embedding)}")
            
            try:
                # Get relevant documents/chunks from ChromaDB
                # Using more results since we might combine chunks
                retrieve_count = n_results * 3 if combine_chunks else n_results
                
                results = self.db_service.query_documents(query_embedding, n_results=retrieve_count)
            except Exception as e:
                # Handle potential embedding dimension mismatch
                error_msg = str(e)
                if "dimension" in error_msg.lower():
                    self.logger.error(f"Embedding dimension error: {error_msg}")
                    return {
                        "query": query,
                        "response": "Error: Embedding dimension mismatch. Please reprocess documents with the current embedding model.",
                        "sources": {"documents": [], "ids": [], "metadatas": []},
                        "status": "error",
                        "error": f"Embedding dimension mismatch. Documents in DB have different dimensions than current model output. {error_msg}"
                    }
                else:
                    # Re-raise other exceptions
                    raise
            
            # Handle the case where no documents are found
            if not results["documents"] or len(results["documents"][0]) == 0:
                return {
                    "query": query,
                    "response": "No relevant documents found in the database.",
                    "sources": {"documents": [], "ids": [], "metadatas": []},
                    "status": "not_found"
                }
            
            # Prepare document data
            docs = results["documents"][0]
            ids = results["ids"][0]
            metadatas = results["metadatas"][0] if "metadatas" in results else [{}] * len(ids)
            distances = results["distances"][0] if "distances" in results else [0] * len(ids)
            
            # Combine chunks from the same document if requested
            if combine_chunks:
                docs, ids, metadatas, distances = self._combine_chunks(docs, ids, metadatas, distances, n_results)
            
            # Get the best matching document (first result)
            best_match = docs[0] if docs else ""
            
            # Generate a response based on the best match using Ollama
            context = best_match
            
            # If the context is too short and we have multiple results, add more context
            # This improves answer quality by providing more information
            if len(context.split()) < 100 and len(docs) > 1:
                context = docs[0] + "\n\n" + docs[1]
            
            # Classify the query to determine if we should use web search
            source_type = "documents"
            confidence = 1.0
            classification_metadata = {}
            
            if web_search is None:  # Auto-classify if not explicitly set
                # Extract document scores for better classification
                doc_distance_scores = distances if distances else []
                # Convert distances to similarity scores (lower distance = higher similarity)
                doc_scores = [1.0 - min(d, 1.0) for d in doc_distance_scores] if doc_distance_scores else []
                
                # Classify the query
                source_type, confidence, classification_metadata = self.query_classifier.classify(
                    query=query, 
                    doc_scores=doc_scores
                )
                self.logger.info(f"Query classified as '{source_type}' with {confidence:.2f} confidence")
            
            # Decide whether to use web search based on classification or explicit setting
            should_use_web = web_search if web_search is not None else (
                source_type == "web" or source_type == "hybrid"
            )
            
            # Add web search results if enabled/auto-determined
            web_results = []
            if should_use_web and self.web_search_client:
                try:
                    self.logger.info(f"Performing web search for query: {query}")
                    web_results = self.web_search_client.search_with_serper(query, num_results=web_results_count)
                    
                    if web_results:
                        # Format web results and add to context
                        web_context = self.web_search_client.format_results_as_context(web_results)
                        context = web_context + "\n\n" + context
                        self.logger.info(f"Added {len(web_results)} web search results to context")
                except Exception as e:
                    self.logger.error(f"Error during web search: {e}")
                    # Continue with only vector DB results
            
            response = self.ollama_client.generate_response(context=context, query=query)
            
            # Clean up the response for better frontend rendering
            cleaned_results = {
                "documents": docs,
                "ids": ids,
                "metadatas": metadatas,
                "distances": distances,
                "combined_chunks": combine_chunks,
                "web_results": web_results if web_results else []
            }
            
            # Prepare response
            response_data = {
                "query": query, 
                "response": response, 
                "sources": cleaned_results,
                "status": "success",
                "web_search_used": len(web_results) > 0,  # Only true if actual web results were found and used
                "source_type": source_type
            }
            
            # Include classification details if requested
            if explain_classification and web_search is None:
                response_data["classification"] = {
                    "source_type": source_type,
                    "confidence": confidence,
                    "explanations": classification_metadata.get("explanations", []),
                    "matched_terms": classification_metadata.get("matched_terms", []),
                    "scores": classification_metadata.get("scores", {})
                }
                
            return response_data
            
        except Exception as e:
            self.logger.error(f"Error in process_query: {e}")
            
            # Provide a more helpful error response
            error_response = {
                "query": query,
                "status": "error",
                "error": str(e)
            }
            
            # Add more context based on the type of error
            if "embed" in str(e).lower():
                error_response["response"] = "Error generating embeddings. The Ollama model may not support the embedding API."
                error_response["suggestion"] = "Check if the model supports embeddings or try a different model."
            elif "chroma" in str(e).lower():
                error_response["response"] = "Error connecting to the vector database."
                error_response["suggestion"] = "Verify ChromaDB is running and accessible."
            else:
                error_response["response"] = f"An error occurred while processing your query: {str(e)}"
                
            error_response["sources"] = {"documents": [], "ids": [], "metadatas": []}
            
            return error_response

    def _combine_chunks(self, 
                       docs: List[str], 
                       ids: List[str], 
                       metadatas: List[Dict[str, Any]], 
                       distances: List[float],
                       n_results: int) -> Tuple[List[str], List[str], List[Dict[str, Any]], List[float]]:
        """
        Combine chunks from the same document for better context.
        
        Args:
            docs: List of document texts
            ids: List of document IDs
            metadatas: List of document metadata
            distances: List of similarity distances
            n_results: Number of combined results to return
            
        Returns:
            Tuple of combined (docs, ids, metadatas, distances)
        """
        # Group by source document
        doc_groups = {}
        
        for i, doc_id in enumerate(ids):
            # Extract source filename from chunk ID or use full ID if not chunked
            source_file = doc_id
            if "#chunk-" in doc_id:
                source_file = doc_id.split("#chunk-")[0]
            
            # Create or update the document group
            if source_file not in doc_groups:
                doc_groups[source_file] = {
                    "content": [],
                    "ids": [],
                    "metadata": [],
                    "distances": [],
                    "avg_distance": 0
                }
            
            doc_groups[source_file]["content"].append(docs[i])
            doc_groups[source_file]["ids"].append(doc_id)
            doc_groups[source_file]["metadata"].append(metadatas[i])
            doc_groups[source_file]["distances"].append(distances[i])
        
        # Calculate average distance for sorting
        for source, group in doc_groups.items():
            group["avg_distance"] = sum(group["distances"]) / len(group["distances"])
        
        # Sort groups by average distance and limit to n_results
        sorted_groups = sorted(doc_groups.items(), key=lambda x: x[1]["avg_distance"])
        top_groups = sorted_groups[:n_results]
        
        # Combine chunks within each group and create the final result
        combined_docs = []
        combined_ids = []
        combined_metadatas = []
        combined_distances = []
        
        for source_file, group in top_groups:
            # Combine all chunks from this document
            combined_text = "\n\n".join(group["content"])
            combined_docs.append(combined_text)
            combined_ids.append(source_file)
            
            # Combine metadata - use the first chunk's metadata as base
            base_meta = group["metadata"][0].copy() if group["metadata"] else {}
            base_meta["chunk_count"] = len(group["content"])
            base_meta["chunks"] = group["ids"]
            combined_metadatas.append(base_meta)
            
            # Use average distance
            combined_distances.append(group["avg_distance"])
            
        return combined_docs, combined_ids, combined_metadatas, combined_distances